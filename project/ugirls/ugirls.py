# -*- coding:UTF-8  -*-
"""
尤果图集预览图片爬虫
http://www.ugirls.com/
@author: hikaru
email: hikaru870806@hotmail.com
如有问题或建议请联系
"""
from common import *
import os
import re
import traceback


# 获取指定页数的图集
def get_album_page(album_id):
    album_url = "http://www.ugirls.com/Content/List/Magazine-%s.html" % album_id
    album_response = net.http_request(album_url, method="GET")
    result = {
        "image_url_list": [],  # 全部图片地址
        "is_delete": False,  # 是不是已经被删除
        "model_name": "",  # 模特名字
    }
    if album_response.status != net.HTTP_RETURN_CODE_SUCCEED:
        raise robot.RobotException(robot.get_http_request_failed_reason(album_response.status))
    if album_response.data.find("该页面不存在,或者已经被删除!") >= 0:
        result["is_delete"] = True
    else:
        # 获取模特名字
        model_info_html = tool.find_sub_string(album_response.data, '<div class="ren_head">', "</div>")
        if not model_info_html:
            raise robot.RobotException("页面截取模特信息失败\n%s" % album_response.data)
        model_name = tool.find_sub_string(model_info_html, 'title="', '"')
        if not model_name:
            raise robot.RobotException("模特信息截取模特名字失败\n%s" % model_info_html)
        result["model_name"] = str(model_name).strip()
        # 获取所有图片地址
        image_info_data = tool.find_sub_string(album_response.data, '<ul id="myGallery">', "</ul>")
        image_url_list = re.findall('<img src="([^"]*)"', image_info_data)
        if len(image_url_list) == 0:
            raise robot.RobotException("页面匹配图片地址失败\n%s" % album_response.data)
        for image_url in image_url_list:
            if image_url.find("_magazine_web_m.") == -1:
                raise robot.RobotException("图片地址不符合规则\n%s" % image_url)
            result["image_url_list"].append(image_url.replace("_magazine_web_m.", "_magazine_web_l."))
    return result


# 从图集首页获取最新的图集id
def get_index_page():
    index_url = "http://www.ugirls.com/Content/"
    index_response = net.http_request(index_url, method="GET")
    result = {
        "max_album_id": None,  # 最新图集id
    }
    if index_response.status != net.HTTP_RETURN_CODE_SUCCEED:
        raise robot.RobotException(robot.get_http_request_failed_reason(index_response.status))
    album_list_html = tool.find_sub_string(index_response.data, '<div class="magazine_list_wrap">', '<div class="xfenye">')
    if not album_list_html:
        raise robot.RobotException("页面截取图集列表失败\n%s" % index_response.data)
    album_id_find = re.findall('href="http://www.ugirls.com/Shop/Detail/Product-(\d*).html" target="_blank"', album_list_html)
    if len(album_id_find) == 0:
        raise robot.RobotException("图集列表匹配图集id失败\n%s" % index_response.data)
    result["max_album_id"] = max(map(int, list(set(album_id_find))))
    return result


class UGirls(robot.Robot):
    def __init__(self):
        sys_config = {
            robot.SYS_DOWNLOAD_IMAGE: True,
            robot.SYS_NOT_CHECK_SAVE_DATA: True,
        }
        robot.Robot.__init__(self, sys_config)

    def main(self):
        # 解析存档文件，获取上一次的图集id
        album_id = 1
        if os.path.exists(self.save_data_path):
            file_save_info = tool.read_file(self.save_data_path)
            if not robot.is_integer(file_save_info):
                log.error("存档内数据格式不正确")
                tool.process_exit()
            album_id = int(file_save_info)
        total_image_count = 0
        temp_path = ""

        try:
            # 获取图集首页
            try:
                index_response = get_index_page()
            except robot.RobotException, e:
                log.error("图集首页解析失败，原因：%s" % e.message)
                raise

            log.step("最新图集id：%s" % index_response["max_album_id"])

            while album_id <= index_response["max_album_id"]:
                log.step("开始解析第%s页图集" % album_id)

                # 获取相册
                try:
                    album_response = get_album_page(album_id)
                except robot.RobotException, e:
                    log.error("第%s页图集解析失败，原因：%s" % (album_id, e.message))
                    raise

                if album_response["is_delete"]:
                    log.step("第%s页图集已被删除，跳过" % album_id)
                    album_id += 1
                    continue

                log.trace("第%s页图集解析的全部图片：%s" % (album_id, album_response["image_url_list"]))

                image_index = 1
                temp_path = album_path = os.path.join(self.image_download_path, "%04d %s" % (album_id, album_response["model_name"]))
                for image_url in album_response["image_url_list"]:
                    log.step("开始下载第%s页图集的第%s张图片 %s" % (album_id, image_index, image_url))

                    file_type = image_url.split(".")[-1]
                    file_path = os.path.join(album_path, "%03d.%s" % (image_index, file_type))
                    save_file_return = net.save_net_file(image_url, file_path)
                    if save_file_return["status"] == 1:
                        log.step("第%s页图集的第%s张图片下载成功" % (album_id, image_index))
                        image_index += 1
                    else:
                         log.error("第%s页图集的第%s张图片 %s 下载失败，原因：%s" % (album_id, image_index, image_url, robot.get_save_net_file_failed_reason(save_file_return["code"])))
                # 图集内图片全部下载完毕
                temp_path = ""  # 临时目录设置清除
                total_image_count += image_index - 1  # 计数累加
                album_id += 1  # 设置存档记录
        except SystemExit, se:
            if se.code == 0:
                log.step("提前退出")
            else:
                log.error("异常退出")
            # 如果临时目录变量不为空，表示某个图集正在下载中，需要把下载了部分的内容给清理掉
            if temp_path:
                path.delete_dir_or_file(temp_path)
        except Exception, e:
            log.error("未知异常")
            log.error(str(e) + "\n" + str(traceback.format_exc()))

        # 重新保存存档文件
        tool.write_file(str(album_id), self.save_data_path, tool.WRITE_FILE_TYPE_APPEND)
        log.step("全部下载完毕，耗时%s秒，共计图片%s张" % (self.get_run_time(), total_image_count))


if __name__ == "__main__":
    UGirls().main()
