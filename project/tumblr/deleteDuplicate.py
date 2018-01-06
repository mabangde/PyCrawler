# -*- coding:UTF-8  -*-
"""
@author: hikaru
email: hikaru870806@hotmail.com
如有问题或建议请联系
"""
from common import *
import os
import csv
DUPLICATE_CSV_FILE_PATH = os.path.realpath("D:\\duplicate.csv")


def main(file_path):
    index = 1
    check_list = []
    with open(file_path) as file_handle:
        csv_reader = csv.DictReader(file_handle)
        for row in csv_reader:
            # 处理一个组别的
            if index != int(row["组别"]):
                deal_one_group(check_list)
                index = int(row["组别"])
                check_list = []
            check_list.append(row)


def deal_one_group(check_list):
    min_post_id = 0
    min_file_path = ""
    delete_list = []
    for row in check_list:
        post_id = int(row["文件名称"].split(".")[0].split("_")[0])
        file_path = os.path.join(row["路径"], row["文件名称"])
        if min_post_id == 0:
            min_post_id = post_id
            min_file_path = file_path
        elif post_id > min_post_id:
            delete_list.append(file_path)
        else:
            delete_list.append(min_file_path)
            min_post_id = post_id
            min_file_path = file_path
    for file_path in delete_list:
        path.delete_dir_or_file(file_path)
        output.print_msg("delete " + file_path)
    output.print_msg("keep " + min_file_path)


if __name__ == "__main__":
    main(DUPLICATE_CSV_FILE_PATH)
