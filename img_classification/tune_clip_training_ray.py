#!/usr/bin/env python
# Filename: hyper_para_ray 
"""
introduction: conduct hyper-parameter tuning using ray: for tuning the parameters of CLIP models

run in :

authors: Huang Lingcao
email:huanglingcao@gmail.com
add time: 11 December, 2024
"""
import shutil

import numpy  # Import numpy first to initialize MKL properly
import os,sys

import pandas as pd
from datetime import datetime
import ray
from ray import tune
from ray.tune import Tuner, TuneConfig
from ray.air import RunConfig, session
from ray.tune.schedulers import ASHAScheduler
import pickle  # Add this import to use pickle for saving/loading checkpoints
import random


# code_dir = os.path.expanduser('~/codes/PycharmProjects/BigImageMapper')
code_dir = os.path.expanduser('~/codes/PycharmProjects/DeeplabforRS')

sys.path.append(code_dir)
import basic_src.io_function as io_function
import basic_src.basic as basic
import parameters

machine_name = os.uname()[1]

# template para (contain para_files)
ini_dir=os.path.expanduser('~/Data/slump_demdiff_classify/ini_files')


def get_CPU_GPU_counts():
    import GPUtil
    # Get all available GPUs
    gpus = GPUtil.getGPUs()
    # Get the number of GPUs
    gpu_count = len(gpus)

    # Get the number of logical CPUs
    cpu_count = os.cpu_count()

    return cpu_count, gpu_count


def modify_parameter(para_file, para_name, new_value):
    import parameters
    parameters.write_Parameters_file(para_file,para_name,new_value)


def trial_name_string(trial):
    """
    Args:
        trial (Trial): A generated trial object.

    Returns:
        trial_name (str): String representation of Trial.
    """
    print('\n\n trial_name_string:\n',trial,'\n\n')
    return str(trial)

def trial_dir_string(trial_id):
    # print('\n\n trial_dir_string:\n',trial,'\n\n')
    # return str(trial)   # should able to have more control on the dirname
    basic.outputlogMessage('trial_id: %s'%trial_id)
    # basic.outputlogMessage('experiment_tag: %s'%experiment_tag)
    return 'clip_tuning_' + str(trial_id)[-6:]  # should not write as [-6:-1], use the last 5 digits + '_'.

def get_top1_accuracy(accuracy_log):
    # Open the file and read its content
    with open(accuracy_log, "r") as file:
        lines = file.readlines()

    # Initialize variable to store the result
    class_1_accuracy = None
    top1_accuracy = None

    # Loop through the lines in reverse order
    for line in reversed(lines):
        if "class: 1, accuracy (top-1)" in line:
            # Extract the accuracy value after the last ":"
            class_1_accuracy = float(line.split(":")[-1].strip())
        if "top 1 accuracy:" in line:
            top1_accuracy  = float(line.split(":")[-1].strip())

        if class_1_accuracy is not None and top1_accuracy is not None:
            break
    return class_1_accuracy, top1_accuracy

def count_lines(filepath):
    with open(filepath, "r") as file:
        return sum(1 for _ in file)

def get_train_valid_samp_count(workdir):
    tmp_list = io_function.get_file_list_by_pattern_ls(workdir,'training_data/*_regions.txt')
    if len(tmp_list) != 1:
        raise IOError(f'not one *_regions.txt in {workdir}/training_data')
    train_txt = tmp_list[0]
    tmp_list = io_function.get_file_list_by_pattern_ls(workdir,'training_data/*_regions_valid.txt')
    if len(tmp_list) != 1:
        raise IOError(f'not one *_regions_valid.txt in {workdir}/training_data')
    valid_txt = tmp_list[0]

    train_samp_count = count_lines(train_txt)
    valid_samp_count = count_lines(valid_txt)
    return train_samp_count, valid_samp_count


def copy_ini_train_files(ini_dir, work_dir, para_file):

    import basic_src.io_function as io_function
    ini_list = [para_file, 'model_clip.ini','s2_rgb_ini_files.txt','finetune_clip.sh']
    for ini in ini_list:
        io_function.copy_file_to_dst(os.path.join(ini_dir, ini ), os.path.join(work_dir,ini), overwrite=True)

def copy_training_data(data_dir, work_dir):
    source_folder = os.path.join(data_dir, 'training_data')
    destination_folder = os.path.join(work_dir,'training_data')
    if os.path.isdir(source_folder):
        try:
            shutil.copytree(source_folder, destination_folder)
            print(f"Folder copied successfully from {source_folder} to {destination_folder}")
        except FileNotFoundError:
            print(f"Error: The source folder '{source_folder}' does not exist.")
        except PermissionError:
            print("Error: Permission denied.")
        except Exception as e:
            print(f"An unexpected error occurred: {e}")
    else:
        raise IOError(f'cannot copy_training_data as {copy_training_data} does not exist')



def objective_top_1_accuracy(lr, train_epoch_nums,model_type,a_few_shot_samp_count):

    import parameters


    para_file = 'main_para.ini'
    work_dir = os.getcwd()
    # change work dir
    # print(datetime.now(), f'change working dir from { work_dir} to {ray_work_dir}')
    # work_dir = os.path.join(ray_work_dir,os.path.basename(work_dir))
    # os.chdir(work_dir)

    # create a training folder
    copy_ini_train_files(ini_dir,work_dir,para_file)

    copy_training_data(ini_dir, work_dir)   # copy training data

    exp_name = parameters.get_string_parameters(para_file, 'expr_name')

    # check if ray create a new folder because previous run dir already exist.
    # e.g., previous dir: "multiArea_deeplabv3P_00000", new dir: "multiArea_deeplabv3P_00000_ce9a"
    # then read the miou directly
    # pre_work_dir = work_dir[:-5]  # remove something like _ce9a
    # if os.path.isdir(pre_work_dir):
    #     accuracy_log = os.path.join(pre_work_dir, 'accuracy_log.txt')
    #     top1_acc_class1 = get_top1_accuracy(accuracy_log)
    #     return top1_acc_class1


    # change para_file
    modify_parameter(os.path.join(work_dir, 'model_clip.ini'),'base_learning_rate',lr)
    modify_parameter(os.path.join(work_dir, 'model_clip.ini'),'train_epoch_num',train_epoch_nums)
    modify_parameter(os.path.join(work_dir, 'model_clip.ini'),'model_type',model_type)

    modify_parameter(os.path.join(work_dir, para_file),'a_few_shot_samp_count',a_few_shot_samp_count)


    # # for the cases, we have same parameter for preparing data, then just copy the data to save time.
    # copy_training_datas(training_data_dir,work_dir)

    # run training
    basic.os_system_exit_code('./finetune_clip.sh > screen_output.txt')

    # remove files to save storage
    os.system('rm -rf exp11')

    accuracy_log = os.path.join(work_dir, 'accuracy_log.txt')
    top1_acc_class1, top1_acc = get_top1_accuracy(accuracy_log)
    train_count, valid_count = get_train_valid_samp_count(work_dir)
    return top1_acc_class1, top1_acc, train_count, valid_count


def training_function(config,checkpoint_dir=None):

    # Hyperparameters
    lr = config["lr"]
    train_epoch_nums = config["epoch_num"]
    model_type = config['model_type']
    a_few_shot_samp_count= config['samp_count']

    # # Restore from checkpoint if provided
    # if checkpoint_dir:
    #     checkpoint_path = os.path.join(checkpoint_dir, "checkpoint.pkl")
    #     if os.path.exists(checkpoint_path):
    #         with open(checkpoint_path, "rb") as f:
    #             checkpoint_data = pickle.load(f)
    #             print(f"Restored checkpoint: {checkpoint_data}")
    #             # Restore any state here (e.g., model weights or iteration count)

    # # Perform training (or simulate training here)
    # overall_miou = objective_overall_miou(
    #     lr, iter_num, batch_size, backbone, buffer_size,
    #     training_data_per, data_augmentation, data_aug_ignore_classes
    # )

    # For debugging, generate a random number to simulate the "overall_miou" metric
    # top_1_accuracy = random.uniform(0, 1)  # Random value between 0 and 1
    # print(f"Generated random top_1_accuracy: {top_1_accuracy}")


    # # Save a checkpoint
    # with tune.checkpoint_dir(step=iter_num) as checkpoint_dir:
    #     checkpoint_path = os.path.join(checkpoint_dir, "checkpoint.pkl")
    #     with open(checkpoint_path, "wb") as f:
    #         pickle.dump({"lr": lr, "iter_num": iter_num}, f)  # Save any necessary state

    top_1_acc_c1, top1_acc, train_count, valid_count = objective_top_1_accuracy(lr, train_epoch_nums,model_type,a_few_shot_samp_count)

    # Feed the score back to Tune.
    session.report({"top_1_accuracy": top1_acc, 'top1_acc_c1':top_1_acc_c1, 'train_count':train_count, 'valid_count':valid_count })

def stop_function(trial_id, result):
    # it turns out that stop_function it to check weather to run more experiments, not to decide whether run one experiment.
    pass

    # exp_folder =  'multiArea_deeplabv3P' + str(trial_id)[-6:]
    # # exp_dir = os.path.join(loc_dir, tune_name,exp_folder)
    # if os.path.isdir(exp_dir):
    #     print("%s exists, skip this experiment"%exp_dir)
    #     return True
    #
    # return False

# tune.choice([1])  # randomly chose one value

def main():

    # for the user defined module in code_dir, need to be imported in functions
    # sys.path.insert(0, code_dir)
    # import parameters
    # import basic_src.io_function as io_function
    # import workflow.whole_procedure as whole_procedure
    # from utility.eva_report_to_tables import read_accuracy_multi_reports


    # if os.path.isdir(ray_work_dir) is False:
    #     io_function.mkdir(ray_work_dir)

    # add code_dir for all workers
    ray.init(
        runtime_env={"env_vars": {"PYTHONPATH": code_dir}}
    )
    #                      "working_dir": ray_work_dir

    loc_dir = "./ray_results"
    tune_name = "tune_clip_para"
    # storage_path = os.path.join(os.path.abspath(loc_dir), tune_name)
    storage_path = os.path.abspath(loc_dir)
    result_dir = os.path.join(storage_path,tune_name)

    # clip_prompt
    clip_prompt_list = ["This is an satellite image of a {}.", "This is an aerial image of a {}.",
                        "This is a sentinel-2 satellite mosiac of a {}.", "This is a DEM difference of a {}."
                                                                          "This is a DEM hillshade of a {}."]
    # all paramaters
    # a_few_shot_samp_count_list = [10, 50, 100, 200, 300, 600, 1000] #
    a_few_shot_samp_count_list = [150] #
    model_type_list = ['RN50', 'RN101', 'RN50x4', 'RN50x16', 'ViT-B/32', 'ViT-B/16', 'ViT-L/14', 'ViT-L/14@336px'] #
    # due to the setting in train_clip.py, train_epoch_num must be >= 100, train_epoch_num%100 =0
    train_epoch_num_list = [100, 200, 300, 500]  #
    base_learning_rate_list = [1e-5, 1e-4, 5e-5]  #

    ##############################################################
    # ## only test a_few_shot_samp_count
    # a_few_shot_samp_count_list = [item for item in range(10, 1001, 10)]  # [10, 50, 100, 200, 300, 600, 1000]
    # model_type_list = ['ViT-L/14'] #
    # # due to the setting in train_clip.py, train_epoch_num must be >= 100, train_epoch_num%100 =0
    # train_epoch_num_list = [300]  #
    # base_learning_rate_list = [1e-5]  #


    # a_few_shot_samp_count_list = [ 10, 50,100, 200, 300, 600, 1000] #
    # # 'ViT-L/14@336px': on ygAlpha (4090D), not enough CUDA memory
    # #  'RN50x16': on ygAlpha (4090D), not enough CUDA memory after 100 epochs
    # model_type_list = ['RN50', 'RN101', 'RN50x4', 'ViT-B/32', 'ViT-B/16', 'ViT-L/14'] # ,
    # # due to the setting in train_clip.py, train_epoch_num must be >= 100, train_epoch_num%100 =0
    # train_epoch_num_list = [100, 200,  300, 500]  #
    # base_learning_rate_list = [1e-5, 1e-4, 5e-5]  #

    # # debugging
    # a_few_shot_samp_count_list = [ 300] #
    # # 'ViT-L/14@336px': on ygAlpha (4090D), not enough CUDA memory
    # #  'RN50x16': on ygAlpha (4090D), not enough CUDA memory after 100 epochs
    # model_type_list = ['RN50', 'RN101', 'RN50x4', 'ViT-B/32', 'ViT-B/16', 'ViT-L/14'] # ,
    # # due to the setting in train_clip.py, train_epoch_num must be >= 100, train_epoch_num%100 =0
    # train_epoch_num_list = [300]  #
    # base_learning_rate_list = [1e-5]  #

    # Check if there are existing folders in the tuning directory
    file_folders = io_function.get_file_list_by_pattern(os.path.join(loc_dir, tune_name), '*')
    b_resume = len(file_folders) > 1

    # Define the search space (same as before)
    param_space = {
        "lr": tune.grid_search(base_learning_rate_list),
        "epoch_num": tune.grid_search(train_epoch_num_list),   # train_epoch_nums
        "model_type": tune.grid_search(model_type_list),
        "samp_count": tune.grid_search(a_few_shot_samp_count_list),  # a_few_shot_samp_count
    }

    # set cpu and gpu count
    cpu_count, gpu_count = get_CPU_GPU_counts()
    if gpu_count > 1:
        gpu_count = 1   #
    if cpu_count > 8:
        cpu_count = 8
    # Wrap the training function with resource requirements
    trainable = tune.with_resources(
        training_function,
        resources={"cpu": cpu_count, "gpu": gpu_count}  # Allocate 24 CPUs and 1 GPU per trial
    )

    if os.path.isdir(result_dir):
        print(f"Resuming from previous session at {result_dir}")
        tuner = Tuner.restore(result_dir,
                              trainable=trainable)
    else:
        print("Starting a new session")
        # Configure the Tuner
        tuner = Tuner(
            trainable=trainable,
            param_space=param_space,
            tune_config=TuneConfig(
                metric="top_1_accuracy",  # Metric to optimize
                mode="max",  # Maximize the metric
                num_samples=1,  # Number of samples (can be tuned as needed)
                scheduler=ASHAScheduler(),  # ASHA scheduler
                reuse_actors=b_resume,  # Resume trials if possible
                trial_name_creator=trial_name_string,
                trial_dirname_creator=trial_dir_string
            ),
            run_config=RunConfig(
                storage_path= f"file://{storage_path}",  # Directory to save results
                name=tune_name,  # Experiment name
                log_to_file=("stdout.log", "stderr.log"),  # Redirect logs
                # trial_name_creator=trial_name_string,  # Custom trial name
                # trial_dirname_creator=trial_dir_string,  # Custom trial directory name
            ),
        )

    # Run the tuner
    results = tuner.fit()

    # Get the best configuration
    best_result = results.get_best_result(metric="top_1_accuracy", mode="max")
    print("Best config: ", best_result.config)

    # Get a DataFrame for analyzing trial results
    df = results.get_dataframe()
    output_file = f'top1_acc_ray_tune_{machine_name}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
    with pd.ExcelWriter(output_file) as writer:
        df.to_excel(writer)
        print(f'Wrote trial results to {output_file}')



if __name__ == '__main__':


    curr_dir_before_ray = os.getcwd()
    print('\n\ncurrent folder before ray tune: ', curr_dir_before_ray, '\n\n')
    ray_work_dir = os.path.join(curr_dir_before_ray, 'ray_workdir')
    main()

