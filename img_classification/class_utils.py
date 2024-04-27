#!/usr/bin/env python
# Filename: class_utils.py 
"""
introduction:

authors: Huang Lingcao
email:huanglingcao@gmail.com
add time: 27 January, 2024
"""



import os,sys
from torch.utils.data.dataset import Dataset
import numpy as np
from PIL import Image
import re

code_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
sys.path.insert(0, code_dir)
import basic_src.io_function as  io_function
import datasets.vector_gpd as vector_gpd
import parameters

class RSVectorDataset(Dataset):
    pass

class RSPatchDataset(Dataset):
    def __init__(self, image_path_list, image_labels, label_txt = 'label.txt', transform=None, test=False):
        self.img_list = image_path_list
        self.labels = image_labels

        label_list = [[item.split(',')[0], int(item.split(',')[1])] for item in io_function.read_list_from_txt(label_txt)]
        # arr_t = np.array(label_list).T
        label_list = np.array(label_list).T.tolist()    # switch the row and column
        self.transform = transform
        self.test = test

        self.classes = label_list[0]

    def __getitem__(self, index):
        im_path = self.img_list[index]
        label = self.labels[index]
        # im_path = os.path.join(self.data_root, 'Images', im_path0)
        im = Image.open(im_path)
        if self.transform is not None:
            im = self.transform(im)

        return im, label, im_path

    def __len__(self):
        return len(self.img_list)

def get_class_labels_from_vector_file(img_path_list, vector_path):
    # the img_path_list are those subImages, generated by "get_subImages.py", using the "vector_path"
    if vector_gpd.is_field_name_in_shp(vector_path,'class_int') is False:
        return [-1]*len(img_path_list)
    shp_label_list = vector_gpd.read_attribute_values_list(vector_path,'class_int')
    label_list = []
    for i_path in img_path_list:
        tmp = os.path.basename(i_path).split('_')[-1]
        idx =int(tmp.split('.')[0])
        label_list.append(shp_label_list[idx])
    return label_list

def get_file_list(input_dir, pattern, area_ini):
    file_list = io_function.get_file_list_by_pattern(input_dir, pattern)
    if len(file_list) < 1:
        raise ValueError('No files for processing, please check directory (%s) and pattern (%s) in %s'
                         % (input_dir, pattern, area_ini))
    return file_list

# copy from dem_common.py
def get_grid_id_from_path(item):
    return int(re.findall(r'grid\d+', os.path.basename(item))[0][4:])

def get_pseudo_labels_path(save_dir, v_num, topk):
    save_path_txt = os.path.join(save_dir, 'pseudo_v{}_train_{}shot.txt'.format(v_num, topk))
    return save_path_txt

def get_model_save_path(train_save_dir, para_file, train_data_txt=''):
    expr_name = parameters.get_string_parameters(para_file, 'expr_name')
    network_ini = parameters.get_string_parameters(para_file, 'network_setting_ini')
    model_type = parameters.get_string_parameters(network_ini, 'model_type')

    model_type = model_type.replace('/','')
    if train_data_txt != '':
        model_type += '_' + os.path.splitext(os.path.basename(train_data_txt))[0]
    file_name = 'model_'+model_type + '_' + expr_name +'.ckpt'
    save_path = os.path.join(train_save_dir,file_name)
    return save_path

def get_training_data_dir(WORK_DIR):
    training_data_dir = os.path.join(WORK_DIR, 'training_data')
    if os.path.isdir(training_data_dir) is False:
        io_function.mkdir(training_data_dir)
    return training_data_dir

def get_merged_training_data_txt(training_data_dir, expr_name, region_count):
    save_path = os.path.join(training_data_dir,
                             'merge_training_data_for_%s_from_%d_regions.txt' % (expr_name, region_count))
    return save_path

def pair_raster_vecor_files_grid(vector_files, raster_files):
    # pair the vector and raster files for each grid based on information in file name
    # e.g. sel_regions_small_S2_SR_grid9226_8bit.tif  : dem_diffs_polygons_grid9226.gpkg
    raster_grid_nums = [get_grid_id_from_path(item) for item in raster_files]
    vector_grid_nums = [get_grid_id_from_path(item) for item in vector_files]

    raster_vector_pairs = {}
    # set vector files as base
    for idx, v_grid in enumerate(vector_grid_nums):
        if v_grid in raster_grid_nums:
            ref_idx = raster_grid_nums.index(v_grid)
            raster_vector_pairs[v_grid] = [vector_files[idx], raster_files[ref_idx]]

    return raster_vector_pairs


def compute_topk_acc(pred, targets, topk):
    """
    Computing top-k accuracy given prediction and target vectors.
    Args:
        pred:    Network prediction
        targets: Ground truth labels
        topk:    k value
    """
    topk = min(topk, pred.shape[1])
    _, pred = pred.topk(topk, 1, True, True)
    pred = pred.t()
    correct = pred.eq(targets.view(1, -1).expand_as(pred))
    hits_tag = correct[:topk].reshape(-1).float().sum(0)

    return hits_tag


def calculate_metrics(outputs, targets):
    """
    Computing top-1 and top-5 accuracy metrics.
    Args:
        outputs: Network outputs list
        targets: Ground truth labels
    """
    pred = outputs

    # Top-k prediction for TAg
    hits_tag_top5 = compute_topk_acc(pred, targets, 5)
    hits_tag_top1 = compute_topk_acc(pred, targets, 1)

    return hits_tag_top5.item(), hits_tag_top1.item()

if __name__ == '__main__':
    pass