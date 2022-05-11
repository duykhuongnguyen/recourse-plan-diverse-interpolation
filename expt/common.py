import numpy as np
import copy
import os
import torch
import joblib
import sklearn
from functools import partialmethod
from sklearn.model_selection import train_test_split
from sklearn.utils import check_random_state
from collections import defaultdict, namedtuple

import dice_ml

from utils import helpers
from utils.data_transformer import DataTransformer
from utils.funcs import compute_max_distance, lp_dist, compute_validity, compute_proximity, compute_diversity, compute_distance_manifold, compute_dpp

from classifiers import mlp, random_forest

from libs.ar import lime_ar, svm_ar, clime_ar, limels_ar
from libs.roar import lime_roar, clime_roar, limels_roar
from libs.mace import mace
from libs.wachter import wachter
from libs.projection import lime_proj
from libs.face import face
from libs.frpd import quad
from libs.dice import dice
from rmpm import rmpm_ar, rmpm_proj, rmpm_roar


# Results = namedtuple("Results", ["l1_cost", "cur_vald", "fut_vald", "feasible"])
Results = namedtuple("Results", ["valid", "l1_cost", "diversity", "manifold_dist", "dpp", "feasible"])


def to_numpy_array(lst):
    pad = len(max(lst, key=len))
    return np.array([i + [0]*(pad-len(i)) for i in lst])


def load_models(dname, cname, wdir):
    pdir = os.path.dirname(wdir)
    pdir = os.path.join(pdir, 'checkpoints')
    models = helpers.pload(f"{cname}_{dname}.pickle", pdir)
    return models


def calc_future_validity(x, shifted_models):
    preds = []
    for model in shifted_models:
        pred = model.predict(x)
        preds.append(pred)
    preds = np.array(preds)
    return np.mean(preds)


def enrich_training_data(num_samples, train_data, cat_indices, rng):
    rng = check_random_state(rng)
    cur_n, d = train_data.shape
    min_f_val = np.min(train_data, axis=0)
    max_f_val = np.max(train_data, axis=0)
    new_data = rng.uniform(min_f_val, max_f_val, (num_samples - cur_n, d))

    # new_data = rng.normal(0, 1, (num_samples - cur_n, d))
    # scaler = StandardScaler()
    # scaler.fit(train_data)
    # new_data = new_data * scaler.scale_ + scaler.mean_

    new_data[:, cat_indices] = new_data[:, cat_indices] >= 0.5

    new_data = np.vstack([train_data, new_data])
    return new_data


def to_mean_std(m, s, is_best):
    if is_best:
        return "\\textbf{" + "{:.2f}".format(m) + "}" + " $\pm$ {:.2f}".format(s)
    else:
        return "{:.2f} $\pm$ {:.2f}".format(m, s)


def _run_single_instance(idx, method, x0, model, shifted_models, seed, logger, params=dict()):
    # logger.info("Generating recourse for instance : %d", idx)

    torch.manual_seed(seed+2)
    np.random.seed(seed+1)
    random_state = check_random_state(seed)

    x_ar, report = method.generate_recourse(x0, model, random_state, params)

    l1_cost = lp_dist(x0, x_ar, p=1)
    cur_vald = model.predict(x_ar)
    fut_vald = calc_future_validity(x_ar, shifted_models)
    # print(l1_cost, cur_vald, fut_vald, report['feasible'])
    # raise ValueError

    return Results(l1_cost, cur_vald, fut_vald, report['feasible'])


def _run_single_instance_plans(idx, method, x0, model, seed, logger, params=dict()):
    # logger.info("Generating recourse for instance : %d", idx)
    torch.manual_seed(seed+2)
    np.random.seed(seed+1)
    random_state = check_random_state(seed)

    df = params['dataframe']
    numerical = params['numerical']
    k = params['k']
    transformer = params['transformer']

    full_dice_data = dice_ml.Data(dataframe=df,
                              continuous_features=numerical,
                              outcome_name='label')
    # transformer = DataTransformer(full_dice_data)

    # x_ar, report = method.generate_recourse(x0, model, random_state, params)
    print("Original instance: ", x0)
    plans, report = method.generate_recourse(x0, model, random_state, params)
    print("Recourse plans: ", plans)

    valid = compute_validity(model, plans)
    l1_cost = compute_proximity(x0, plans, p=2)
    diversity = compute_diversity(plans, transformer.data_interface)
    manifold_dist = compute_distance_manifold(plans, params['train_data'], params['k'])
    dpp = compute_dpp(plans)

    return Results(valid, l1_cost, diversity, manifold_dist, dpp, report['feasible'])

method_name_map = {
    "lime_ar": "LIME-AR",
    "mpm_ar": "MPM-AR",
    "clime_ar": "CLIME-AR",
    "limels_ar": "LIMELS-AR",
    "quad_rmpm_ar": "QUAD-MPM-AR",
    "bw_rmpm_ar": "BW-MPM-AR",
    "fr_rmpm_ar": "FR-MPM-AR",
    "lime_roar": "LIME-ROAR",
    "clime_roar": "CLIME-ROAR",
    "limels_roar": "LIMELS-ROAR",
    "mace": "MACE",
    "wachter": "Wachter",
    "lime_proj": "LIME-PROJ",
    "mpm_proj": "MPM-RPOJ",
    "fr_rmpm_proj": "FR-MPM-PROJ",
    "quad_rmpm_proj": "QUAD-MPM-PROJ",
    "bw_rmpm_proj": "BW-MPM-PROJ",
    "mpm_roar": "MPM-ROAR",
    "quad_rmpm_roar": "QUAD-MPM-ROAR",
    "bw_rmpm_roar": "BW-MPM-ROAR",
    'fr_rmpm_roar': "FR-MPM-ROAR",
    'fr_rmpm_roar_rho': "FR-MPM-ROAR (1)",
    'fr_rmpm_roar_delta': "FR-MPM-ROAR (2)",
    'face': "FACE",
    'frpd_quad': 'FRPD-QUAD',
    'dice': 'DICE',
}


dataset_name_map = {
    "synthesis": "Synthetic data",
    "german": "German",
    "sba": "SBA",
    "bank": "Bank",
    "student": "Student",
}

metric_order = {'cost': -1, 'valid': 1, 'diversity': 0, 'manifold_dist': -1, 'dpp': -1}


method_map = {
    "lime_ar": lime_ar,
    "mpm_ar": rmpm_ar,
    "clime_ar": clime_ar,
    "limels_ar": limels_ar,
    "quad_rmpm_ar": rmpm_ar,
    "bw_rmpm_ar": rmpm_ar,
    "fr_rmpm_ar": rmpm_ar,
    "mace": mace,
    "wachter": wachter,
    "lime_proj": lime_proj,
    "mpm_proj": rmpm_proj,
    "quad_rmpm_proj": rmpm_proj,
    "bw_rmpm_proj": rmpm_proj,
    "fr_rmpm_proj": rmpm_proj,
    "lime_roar": lime_roar,
    "clime_roar": clime_roar,
    "limels_roar": limels_roar,
    "mpm_roar": rmpm_roar,
    "quad_rmpm_roar": rmpm_roar,
    "bw_rmpm_roar": rmpm_roar,
    "fr_rmpm_roar": rmpm_roar,
    "face": face,
    "frpd_quad": quad,
    "dice": dice,
}




clf_map = {
    "net0": mlp.Net0,
    "mlp": mlp.Net0,
    "rf": random_forest.RandomForest,
}


train_func_map = {
    'net0': mlp.train,
    'mlp': mlp.train,
    'rf': random_forest.train,
}


synthetic_params = dict(num_samples=1000,
                        x_lim=(-2, 4), y_lim=(-2, 7),
                        f=lambda x, y: y >= 1 + x + 2*x**2 + x**3 - x**4,
                        random_state=42)


synthetic_params_mean_cov = dict(num_samples=1000, mean_0=None, cov_0=None, mean_1=None, cov_1=None, random_state=42)
