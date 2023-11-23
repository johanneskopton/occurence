import matplotlib.pyplot as plt
import numpy as np
import sklearn.metrics
import sklearn.model_selection

from minkowski import Data
plt.style.use("ggplot")


class Predictor:
    def __init__(
        self,
        data: Data,
        covariate_model: sklearn.base.ClassifierMixin,
        cv_splits: int = 5,
    ):
        self._data = data
        self._cv_splits = cv_splits

        self._cov_model = covariate_model
        self._X = self._data.get_training_covariates()
        self._y = self._data.predictand

        self._cross_val_res = None

        self._is_binary = self._data.predictand.dtype == bool

    def fit_covariate_model(self, train_idxs=None):
        if train_idxs is None:
            self._cov_model.fit(self._X, self._y)
        else:
            self._cov_model.fit(self._X[train_idxs, :], self._y[train_idxs])

    def get_covariate_probability(self, idxs=slice(None)):
        if self._is_binary:
            return self._cov_model.predict_proba(self._X[idxs])[:, 1]
        else:
            return self._cov_model.predict(self._X[idxs])

    def predict_covariate_probability(self, df):
        X = self._data.prepare_covariates(df)

        if self._is_binary:
            return self._cov_model.predict_proba(X)[:, 1]
        else:
            return self._cov_model.predict(X)

    def get_residuals(self, idxs=slice(None)):
        return self.get_covariate_probability(idxs) - self._y[idxs]

    def calc_cross_validation(self):
        cv = sklearn.model_selection.TimeSeriesSplit(n_splits=self._cv_splits)
        ground_truth = []
        prediction = []
        for fold, (train, test) in enumerate(cv.split(self._X, self._y)):
            self.fit_covariate_model(train)
            ground_truth.append(self._y[test])
            prediction.append(self.get_covariate_probability(test))

        self._cross_val_res = ground_truth, prediction

    def get_cross_val_metric(self, metric):
        if self._cross_val_res is None:
            self.calc_cross_validation()

        ground_truth, prediction = self._cross_val_res

        res = []
        for i in range(self._cv_splits):
            res.append(metric(ground_truth[i], prediction[i]))
        return res

    def plot_cross_validation_roc(self):
        if self._cross_val_res is None:
            self.calc_cross_validation()

        tprs = []
        aucs = []
        mean_fpr = np.linspace(0, 1, 100)
        fig, ax = plt.subplots(figsize=(6, 6))

        ground_truth, pred_probability, pred = self._cross_val_res

        for fold in range(self._cv_splits):
            viz = sklearn.metrics.RocCurveDisplay.from_predictions(
                ground_truth[fold],
                pred_probability[fold],
                name=f"ROC fold {fold}",
                alpha=0.3,
                lw=1,
                ax=ax,
                # compatibility with older sklearn and cuml
                # plot_chance_level=(fold == self._cv_splits - 1),
            )
            interp_tpr = np.interp(mean_fpr, viz.fpr, viz.tpr)
            interp_tpr[0] = 0.0
            tprs.append(interp_tpr)
            aucs.append(viz.roc_auc)

        mean_tpr = np.mean(tprs, axis=0)
        mean_tpr[-1] = 1.0
        mean_auc = sklearn.metrics.auc(mean_fpr, mean_tpr)
        std_auc = np.std(aucs)
        ax.plot(
            mean_fpr,
            mean_tpr,
            color="b",
            label=r"Mean ROC (AUC = %0.2f $\pm$ %0.2f)" % (
                mean_auc, std_auc,
            ),
            lw=2,
            alpha=0.8,
        )

        std_tpr = np.std(tprs, axis=0)
        tprs_upper = np.minimum(mean_tpr + std_tpr, 1)
        tprs_lower = np.maximum(mean_tpr - std_tpr, 0)
        ax.fill_between(
            mean_fpr,
            tprs_lower,
            tprs_upper,
            color="grey",
            alpha=0.2,
            label=r"$\pm$ 1 std. dev.",
        )

        ax.set(
            xlim=[-0.05, 1.05],
            ylim=[-0.05, 1.05],
            xlabel="False Positive Rate",
            ylabel="True Positive Rate",
            title="Mean ROC curve with variability\n(TimeSeriesPrediction)",
        )
        ax.axis("square")
        ax.legend(loc="lower right")
        plt.show()
