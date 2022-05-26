import argparse

from expt.config import Config


class Expt3(Config):
    __dictpath__ = 'ec.e3'

    all_clfs = ['net0']
    all_datasets = ['synthesis']

    face_params = {
        "mode": "knn",
        "fraction": 1.0,
    }

    frpd_params = {
        "theta": 0.99,
        "kernel": 1.0,
        "period": 20,
        "response": True,
        "interpolate": "linear",
        "greedy": True,
    }

    dice_params = {
        "proximity_weight": 0.5,
        "diversity_weight": 1.0,
    }

    k = 3

    num_samples = 1000
    max_ins = 100
    max_distance = 1.0


class Expt4(Config):
    __dictpath__ = 'ec.e4'

    all_clfs = ['net0']
    all_datasets = ['synthesis']

    frpd_params = {
        "theta": 0.99,
        "kernel": 1.0,
        "period": 20,
        "response": True,
        "interpolate": "linear",
        "greedy": True,
    }

    dice_params = {
        "proximity_weight": 0.5,
        "diversity_weight": 1.0,
    }   

    params_to_vary = {
        'theta': {
            'default': 0.5,
            'min': 0.2,
            'max': 1.0,
            'step': 0.04,
        },
        'diversity_weight': {
            'default': 1.0,
            'min': 0.0,
            'max': 10.0,
            'step': 0.5,
        },
    }

    k = 3
    num_samples = 1000
    max_ins = 20


class ExptConfig(Config):
    __dictpath__ = 'ec'

    e3 = Expt3()
    e4 = Expt4()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Configuration')
    parser.add_argument('--dump', default='config.yml', type=str)
    parser.add_argument('--load', default=None, type=str)
    parser.add_argument('--mode', default='merge_cls', type=str)

    args = parser.parse_args()
    if args.load is not None:
        ExptConfig.from_file(args.load)
    ExptConfig.to_file(args.dump, mode=args.mode)
