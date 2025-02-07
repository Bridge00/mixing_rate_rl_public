import os 
import yaml
import warnings
import pickle
import numpy as np
import ray
import matplotlib.pyplot as plt
from collections import deque, namedtuple
from itertools import product


import inforatio.envs as envs


class IOManager:
    """
    """

    def __init__(self, output_dir, **kwargs):
        try:
            os.mkdir(output_dir)
        except FileExistsError:
            msg = f'Directory {output_dir} already exists! ' + \
                    'Writing into it, but this may overwrite existing data.'
            warnings.warn(msg.format(output_dir))
        self.output_dir = output_dir

        self.print_interval   = kwargs.get('print_interval')   or 100000
        self.log_interval   = kwargs.get('log_interval')   or 100000
        self.agent_name = kwargs.get('agent_name') or 'UnspecifiedAgent'
        self.filename   = kwargs.get('filename')   or f'{self.agent_name}_ratios'

    def print(self, dont_skip, **kwargs):
        
        if dont_skip:
            defaults = {'episode': None,
                        'cost': None,
                        'entropy': None,
                        'info_ratio': None}
            defaults.update(kwargs)
            kwargs = defaults

            if ((kwargs['episode'] + 1) % self.print_interval) == 0:
                print(' '.join([f'{self.agent_name}',
                                f'ep. {kwargs["episode"]}:',
                                f'J_c {kwargs["cost"]:.2f},',
                                f'H(d) {kwargs["entropy"]:.2f},',
                                f'IR {kwargs["info_ratio"]:.2f}']))

    def log(self, dont_skip, **kwargs):
        """
        This function is called at each step of the training loop to (selectively)
        log training information to a specified log output during the loop.
    
        Any callback with this signature may be used instead, but this is a
        reasonable default behavior.
        """

        if (kwargs.get('force') or
            (dont_skip and ((kwargs['episode'] + 1) % self.log_interval) == 0)):

            defaults = {'episode': None,
                        'costs': None,
                        'entropies': None,
                        'info_ratios': None,
                        'policy': None}
            defaults.update(kwargs)
            kwargs = defaults

            costs_file = os.path.join(self.output_dir, 'costs.npy')
            entropies_file = os.path.join(self.output_dir, 'entropies.npy')
            info_ratios_file = os.path.join(self.output_dir, 'info_ratios.npy')

            np.save(costs_file, kwargs['costs'])
            np.save(entropies_file, kwargs['entropies'])
            np.save(info_ratios_file, kwargs['info_ratios'])

            policy_file = os.path.join(self.output_dir, 'policy.pkl')

            with open(policy_file, 'wb') as f:
                pickle.dump(kwargs['policy'], f)

    def plot(self, dont_skip, **kwargs):
        """
        This function is called at each step of the training loop to (selectively)
        plot training information to a specified output directory during the loop.
    
        Any callback with this signature may be used instead, but this is a
        reasonable default behavior.
        """

        # TODO
        raise NotImplementedError

    def save_yml(self, filename, dictionary):
        yaml_file = os.path.join(self.output_dir, filename + '.yml')
        with open(yaml_file, 'w') as f:
            f.write(yaml.safe_dump(dictionary))


class TrialRunner:
    """
    Given an environment and an agent, do training and store the results.
    """

    def __init__(self, env, agent, io_manager, **kwargs):
        """
        Params
        ------
        env        : an OpenAI gym environment (instantiated)
        agent      : an agent (instantiated)
        io_manager : an IOManager (instantiated)
        kwargs     : dict 
         - width (default = 100)
           The width of the simple moving average window for computation of the
           reward+cost ratios.
         - n_episodes (default = 1)
           Number of episodes.
         - n_steps (default = 100000)
           Number of training steps per episode.
         - log (default = True)
           Whether the experiment will save ratios to a file.
         - plot (default = False)
           Whether the experiment will save plot summaries of the ratios.
         - print (default = True)
           Whether the experiment will print provisional info to stdout.
         - print_interval (default = 10000)
           How frequently the agent should print provisional data to stdout.
         - log_interval (default = 10000)
           How frequently the agent should log provisional data.
         - agent_name
           Name of the agent.
        """
        self.env   = env
        self.agent = agent
        self.io    = io_manager

        defaults = {'width': 100,
                    'n_episodes': 1,
                    'n_steps': 100_000,
                    'log': True,
                    'plot': False,
                    'print': True,
                    'print_interval': 10000,
                    'log_interval': 10000,
                    'agent_name': type(agent).__name__}
        defaults.update(kwargs)
        self.__dict__.update(**defaults)

    def train(self):
        """
        Train a predefined agent on an initialized environment for a specified
        number of steps. Returns the agent's ratio at each step of the training.
        """
    
        costs, entropies, info_ratios = [], [], []
        
        self.env.reset()
    
        # for episode in range(self.n_episodes):
        for episode in range(self.n_episodes):
            cost, entropy, info_ratio = self.agent.update(
                self.env, self.n_steps)
            costs.append(cost)
            entropies.append(entropy)
            info_ratios.append(info_ratio)

            self.io.print(self.print,
                          episode=episode,
                          cost=cost,
                          entropy=entropy,
                          info_ratio=info_ratio)
            self.io.log(self.log,
                        episode=episode,
                        costs=costs,
                        entropies=entropies,
                        info_ratios=info_ratios,
                        policy=self.agent.pi)

        self.io.print(self.print,
                      episode=episode,
                      cost=cost,
                      entropy=entropy,
                      info_ratio=info_ratio)
        self.io.log(self.log,
                    episode=episode,
                    costs=costs,
                    entropies=entropies,
                    info_ratios=info_ratios,
                    policy=self.agent.pi,
                    force=True)

        return info_ratios


# Definitions for ExperimentRunner class

# Namedtuple for saving configuration dictionaries corresponding to trials.
# Each element in a ConfigTuple is a dictionary, e.g. the entry indexed
# by 'env_config' is a dictionary containing all info necessary to create
# an environment. Using a namedtuple ensures that the elements in each
# tuple can be accessed by name, which increases extensibility.
ConfigTuple = namedtuple('ConfigTuple',
                         ['env_config',
                          'agent_config',
                          'iomanager_config',
                          'trial_config',
                          'all_configs_dict'])

class ConfigGenerator:
    """
    Generates configuration dictionaries that define the experiment
    ExperimentRunner is to carry out.

    Stores an experiment specification, which will likely be either a function
    or file. Generates or returns a list of namedtuples
        ConfigTuple(env_config=env_config,
                    agent_config=agent_config,
                    iomanager_config=iomanager_config)
    containing all information needed to create a corresponding TrialRunner.
    """
    def __init__(self, experiment_spec):
        self.experiment_spec = experiment_spec
        raise NotImplementedError
    
    def generate_configs(self):
        """
        Return experiment_configs list. Each element in the list should be a
        ConfigTuple.
        """
        raise NotImplementedError

class ExperimentRunner:
    """
    Overall coordinator of the experiment specified by ConfigGenerator.

    The only Ray objects that will be used are remote actor versions
    of TrialRunners.
    """
    def __init__(self):
        # TODO: decide if trial_coordinator should be saved -- it is
        # holding on to references to Ray actors, preventing them from
        # being garbage collected. The references are only held until
        # the next call to run_experiment(), however.
        self.experiment_configs = None
        self.ray_configs = None
        self.ray_controller = RayController(self)
        self.trial_constructor = None
        self.trial_coordinator = None

    def register_experiment_configs(self, experiment_configs):
        """
        Parse and store experiment_configs.

        For now experiment_configs is just a list of namedtuples of the form
            ConfigTuple(env_config=env_config,
                        agent_config=agent_config,
                        iomanager_config=iomanager_config)
        where each entry is a dictionary, and each namedtuple completely specifies
        a trial to be run.
        """
        self.experiment_configs = experiment_configs


    def register_ray_configs(self, ray_configs):
        """
        Parse and store ray_configs.

        For now ray_configs is simply a dictionary of the form
            {'num_cpus': int,
             'num_gpus': int,
             'cpus_per_trial': int,
             'gpus_per_trial': int}
        num_cpus and num_gpus are needed when starting Ray in RayController,
        while cpus_per_trial and gpus_per_trial are needed when defining
        RayTrialRunner inside TrialConstructor. All four values are needed
        when checking whether num_cpus and num_gpus are sufficient for
        cpus_per_trial and gpus_per_trial, given the number of trials
        specified in experiment_configs.
        """
        self.ray_configs = ray_configs
        self.__dict__.update(self.ray_configs)

    def verify_configs(self):
        """
        Make sure we have enough resources to run all trials in parallel with
        the desired number of cpus and gpus per trial. If not, raise an error.

        Check inside experiment_configs to ensure that no two TrialRunners
        will attempt to write to the same directory. If a conflict is found,
        raise an error.

        This must be called before initialize_ray() and run_experiment()!
        """
        sufficient_cpus = len(self.experiment_configs) * self.cpus_per_trial \
                <= self.num_cpus
        sufficient_gpus = len(self.experiment_configs) * self.gpus_per_trial \
                <= self.num_gpus

        assert sufficient_cpus and sufficient_gpus, 'Not enough resources.'
        
        # TODO Find better way to retrieve output_dir than indexing like this!
        output_dirs = [trial_tuple.iomanager_config['args'][0] \
                       for trial_tuple in self.experiment_configs]

        assert len(set(output_dirs)) == len(self.experiment_configs), \
                'Each trial must write to a distinct output directory.'

    def initialize_ray(self):
        """
        Initialize Ray with the specified ray_configs. If Ray is already running,
        first shut it down, then initialize.

        This must be called after verify_configs() and before run_experiment().
        """
        self.ray_controller.start_ray()

    def shutdown_ray(self):
        """
        Shut Ray down.
        """
        self.ray_controller.stop_ray()

    def run_experiment(self):
        """
        Run the experiment specified by the current experiment_configs. Ray must
        already be initialized with the desired ray_configs and verify_configs()
        should already have been called.

        First, a TrialConstructor and a TrialCoordinator are created. Next,
        TrialConstructor defines the RayTrialRunner object according to the
        ray_configs. It's necessary to define a new RayTrialRunner every time
        the experiment is run in order to allocate it the user-specified resources
        (e.g. num_cpus, num_gpus) contained in ray_configs. Third,
        TrialConstructor constructs a RayTrialRunner remote actor for each of the
        trials defined by experiment_configs. The Ray object IDs for the
        RayTrialRunners are then handed off to the TrialCoordinator, which
        stores them and launches them as Ray remote tasks. Once all tasks
        have been completed (which means all trials have been successfully
        run and logging data saved to disk), the function returns and it is
        safe to call shutdown_ray().

        Note that run_experiment() can be called multiple times over the life of
        ExperimentRunner, potentially on different experiment_configs and
        ray_configs. The only requirements are that Ray must be running and
        verify_configs should be called on the current experiment_configs and
        ray_configs to ensure they are compatible.
        """
        self.trial_constructor = TrialConstructor(self)
        self.trial_coordinator = TrialCoordinator(self)

        self.trial_constructor.define_ray_trial_runner()
        trials = self.trial_constructor.create_trials()

        self.trial_coordinator.gather_trials(trials)
        return_vals = self.trial_coordinator.launch_trials()

        return return_vals


class RayController:
    """
    Starts and stops Ray. Uses the ray_configs stored inside ExperimentRunner
    to decide how to initialize Ray.
    """
    def __init__(self, experiment_runner):
        self.experiment_runner = experiment_runner
        self.ray_running = False

    def _get_ray_init_configs(self):
        """
        Retrieve key-value pairs from ray_configs in EnvironmentRunner
        that must be passed to ray.init() in start_ray().
        """
        ray_configs = self.experiment_runner.ray_configs
        return {key: ray_configs[key] for key in ['num_cpus', 'num_gpus']}

    def start_ray(self):
        """
        Initialize Ray with the desired ray_configs in EnvironmentRunner.
        """
        ray.init(**self._get_ray_init_configs())
        self.ray_running = ray.is_initialized()
        assert self.ray_running, "Ray was not initialized for some reason!"

    def stop_ray(self):
        """
        Shut down Ray.
        """
        assert self.ray_running, "Ray must be running in order to be shut down"
        ray.shutdown()


class TrialConstructor:
    """
    Using the experiment_configs and ray_configs stored inside
    ExperimentRunner, creates corresponding RayTrialRunners to be handed off
    to TrialCoordinator.
    """
    def __init__(self, experiment_runner):
        self.experiment_runner = experiment_runner
        self.RayTrialRunner = None
        self.env_constructor = EnvConstructor()
        self.agent_constructor = AgentConstructor()
        self.iomanager_constructor = IOManagerConstructor()

    def _get_ray_actor_configs(self):
        """
        Retrieve key-value pairs from ray_configs in ExperimentRunner that
        need to be passed to @ray.remote in define_ray_trial_runner().
        """
        ray_configs = self.experiment_runner.ray_configs
        keys = ['num_cpus', 'num_gpus']
        vals = [ray_configs[key] for key in ['cpus_per_trial', 'gpus_per_trial']]
        return dict(zip(keys, vals))

    def define_ray_trial_runner(self):
        """
        Define the RayTrialRunner Ray Actor with the configuration
        (e.g. num_cpus, num_gpus) specified in ExperimentRunner's ray_configs.

        Must be called before create_trials().
        """
        @ray.remote(**self._get_ray_actor_configs())
        class RayTrialRunner(TrialRunner):
            def __init__(self, env, agent, io_manager, **kwargs):
                super().__init__(env, agent, io_manager, **kwargs)

        self.RayTrialRunner = RayTrialRunner

    def create_trials(self):
        """
        Create RayTrialRunners and return a list of their Ray object ids.

        Must be called after define_ray_trial_runner().
        """
        experiment_configs = self.experiment_runner.experiment_configs
        trials = []
        for trial_tuple in experiment_configs:
            env_config, agent_config, iomanager_config, trial_config, config = \
                    trial_tuple.env_config, \
                    trial_tuple.agent_config, \
                    trial_tuple.iomanager_config, \
                    trial_tuple.trial_config, \
                    trial_tuple.all_configs_dict
            env = self.env_constructor.create(env_config)
            agent = self.agent_constructor.create(agent_config)
            iomanager = self.iomanager_constructor.create(
                iomanager_config)
            iomanager.save_yml('config', config)
            trials.append(self.RayTrialRunner.remote(
                env, agent, iomanager, **trial_config))

        return trials

    
class Constructor:
    """
    Constructor super class
    """
    def create(self, config):
        """
        Params
        ------
        config : dict
            'class'  : Python class 
            'args'   : constructor args (list)
            'kwargs' : constructor kwargs  (dict)
        """
        return config['class'](*config['args'], **config['kwargs'])


class EnvConstructor(Constructor):
    """
    Constructs environments.
    """


class AgentConstructor(Constructor):
    """
    Constructs agents.
    """


class IOManagerConstructor(Constructor):
    """
    Constructs IOManagers.
    """


class TrialCoordinator:
    """
    Coordinates execution of trials.

    """
    def __init__(self, experiment_runner):
        self.experiment_runner = experiment_runner
        self.trials = None

    def gather_trials(self, trials):
        """
        Store list of RayTrialRunners to be run.
        """
        self.trials = trials

    def launch_trials(self):
        """
        Launch the experiment. Catch the return values and return them.

        This call is where most of the time will be spent during a call
        to ExperimentRunner.run_experiment(). ray.get() is blocking and
        will not return until all RayTrialRunners have finished executing.
        """
        return_vals = ray.get([trial.train.remote() for trial in self.trials])

        return return_vals
