# -*- coding:UTF-8  -*-
"""
图虫图片爬虫
https://tuchong.com/
@author: hikaru
email: hikaru870806@hotmail.com
如有问题或建议请联系
"""
from common import *
import os
import threading
import time
import traceback

ACCOUNT_LIST = {}
IMAGE_COUNT_PER_PAGE = 20  # 每次请求获取的图片数量
TOTAL_IMAGE_COUNT = 0
IMAGE_DOWNLOAD_PATH = ""
NEW_SAVE_DATA_PATH = ""
IS_DOWNLOAD_IMAGE = True


# 获取账号首页
def get_account_index_page(account_name):
    if robot.is_integer(account_name):
        account_index_url = "https://tuchong.com/%s" % account_name
    else:
        account_index_url = "https://%s.tuchong.com" % account_name
    account_index_response = net.http_request(account_index_url, method="GET", is_auto_redirect=False)
    result = {
        "account_id": None,  # account id（字母账号->数字账号)
    }
    if account_index_response.status == net.HTTP_RETURN_CODE_SUCCEED:
        account_id = tool.find_sub_string(account_index_response.data, 'site_id":"', '",')
        if not account_id:
            raise robot.RobotException("页面截取site id失败\n%s" % account_index_response.data)
        if not robot.is_integer(account_id):
            raise robot.RobotException("site id类型不正确\n%s" % account_index_response.data)
        result["account_id"] = account_id
    elif account_index_response.status == 301 and account_index_response.getheader("Location") == "https://tuchong.com/":
        raise robot.RobotException("账号不存在")
    else:
        raise robot.RobotException(robot.get_http_request_failed_reason(account_index_response.status))
    return result


# 获取指定时间点起的一页相册信息列表
# account_name -> deer-vision
# account_id -> 1186455
# post_time -> 2016-11-11 11:11:11
def get_one_page_album(account_id, post_time):
    # https://deer-vision.tuchong.com/rest/sites/1186455/posts/2016-11-11%2011:11:11?limit=20
    album_pagination_url = "https://www.tuchong.com/rest/sites/%s/posts/%s" % (account_id, post_time)
    query_data = {"limit": IMAGE_COUNT_PER_PAGE}
    album_pagination_response = net.http_request(album_pagination_url, method="GET", fields=query_data, json_decode=True)
    result = {
        "album_info_list": [],  # 全部图片信息
        "is_error": False,  # 是不是格式不符合
    }
    if album_pagination_response.status != net.HTTP_RETURN_CODE_SUCCEED:
        raise robot.RobotException(robot.get_http_request_failed_reason(album_pagination_response.status))
    if not robot.check_sub_key(("posts", "result"), album_pagination_response.json_data):
        raise robot.RobotException("返回数据'posts'或者'result'字段不存在\n%s" % album_pagination_response.json_data)
    if album_pagination_response.json_data["result"] != "SUCCESS":
        raise robot.RobotException("返回数据'result'字段取值不正确\n%s" % album_pagination_response.json_data)
    for album_info in album_pagination_response.json_data["posts"]:
        result_image_info = {
            "album_id": None,  # 相册id
            "album_time": None,  # 相册创建时间
            "album_title": "",  # 相册标题
            "image_url_list": [],  # 全部图片地址
        }
        # 获取相册id
        if not robot.check_sub_key(("post_id",), album_info):
            raise robot.RobotException("相册信息'post_id'字段不存在\n%s" % album_info)
        if not robot.is_integer(album_info["post_id"]):
            raise robot.RobotException("相册信息'post_id'字段类型不正确\n%s" % album_info)
        result_image_info["album_id"] = str(album_info["post_id"])
        # 获取相册标题
        result_image_info["album_title"] = str(album_info["title"].encode("UTF-8"))
        # 获取图片地址
        for image_info in album_info["images"]:
            if not robot.check_sub_key(("img_id",), image_info):
                raise robot.RobotException("相册信息'img_id'字段不存在\n%s" % album_info)
            result_image_info["image_url_list"].append("https://photo.tuchong.com/%s/f/%s.jpg" % (account_id, str(image_info["img_id"])))
        if len(result_image_info["image_url_list"]) == 0:
            raise robot.RobotException("相册信息匹配图片地址失败\n%s" % album_info)
        # 获取相册创建时间
        if not robot.check_sub_key(("published_at",), album_info):
            raise robot.RobotException("相册信息'published_at'字段不存在\n%s" % album_info)
        result_image_info["album_time"] = str(album_info["published_at"])
        result["album_info_list"].append(result_image_info)
    return result


class TuChong(robot.Robot):
    def __init__(self):
        global IMAGE_DOWNLOAD_PATH
        global NEW_SAVE_DATA_PATH
        global IS_DOWNLOAD_IMAGE

        sys_config = {
            robot.SYS_DOWNLOAD_IMAGE: True,
        }
        robot.Robot.__init__(self, sys_config)

        # 设置全局变量，供子线程调用
        IMAGE_DOWNLOAD_PATH = self.image_download_path
        IS_DOWNLOAD_IMAGE = self.is_download_image
        NEW_SAVE_DATA_PATH = robot.get_new_save_file_path(self.save_data_path)

    def main(self):
        global ACCOUNT_LIST

        # 解析存档文件
        # account_id  last_post_id
        ACCOUNT_LIST = robot.read_save_data(self.save_data_path, 0, ["", "0"])

        # 循环下载每个id
        main_thread_count = threading.activeCount()
        for account_id in sorted(ACCOUNT_LIST.keys()):
            # 检查正在运行的线程数
            if threading.activeCount() >= self.thread_count + main_thread_count:
                self.wait_sub_thread()

            # 提前结束
            if not self.is_running():
                break

            # 开始下载
            thread = Download(ACCOUNT_LIST[account_id], self)
            thread.start()

            time.sleep(1)

        # 检查除主线程外的其他所有线程是不是全部结束了
        while threading.activeCount() > main_thread_count:
            self.wait_sub_thread()

        # 未完成的数据保存
        if len(ACCOUNT_LIST) > 0:
            tool.write_file(tool.list_to_string(ACCOUNT_LIST.values()), NEW_SAVE_DATA_PATH)

        # 重新排序保存存档文件
        robot.rewrite_save_file(NEW_SAVE_DATA_PATH, self.save_data_path)

        log.step("全部下载完毕，耗时%s秒，共计图片%s张" % (self.get_run_time(), TOTAL_IMAGE_COUNT))


class Download(robot.DownloadThread):
    def __init__(self, account_info, main_thread):
        robot.DownloadThread.__init__(self, account_info, main_thread)
        self.account_name = self.account_info[0]
        log.step(self.account_name + " 开始")

    # 获取所有可下载相册
    def get_crawl_list(self, account_id):
        post_time = time.strftime('%Y-%m-%d %H:%M:%S')
        album_info_list = []
        is_over = False
        # 获取全部还未下载过需要解析的相册
        while not is_over:
            self.main_thread_check()  # 检测主线程运行状态
            log.step(self.account_name + " 开始解析%s后的一页相册" % post_time)

            # 获取一页相册
            try:
                album_pagination_response = get_one_page_album(account_id, post_time)
            except robot.RobotException, e:
                log.error(self.account_name + " %s后的一页相册解析失败，原因：%s" % (post_time, e.message))
                raise

            # 如果为空，表示已经取完了
            if len(album_pagination_response["album_info_list"]) == 0:
                break

            log.trace(self.account_name + " %s后的一页相册：%s" % (post_time, album_pagination_response["album_info_list"]))

            # 寻找这一页符合条件的相册
            for album_info in album_pagination_response["album_info_list"]:
                # 检查是否达到存档记录
                if int(album_info["album_id"]) > int(self.account_info[1]):
                    album_info_list.append(album_info)
                    post_time = album_info["album_time"]
                else:
                    is_over = True
                    break

        return album_info_list

    # 解析单个相册
    def crawl_album(self, album_info):
        image_index = 1
        # 过滤标题中不支持的字符
        title = path.filter_text(album_info["album_title"])
        if title:
            post_path = os.path.join(IMAGE_DOWNLOAD_PATH, self.account_name, "%s %s" % (album_info["album_id"], title))
        else:
            post_path = os.path.join(IMAGE_DOWNLOAD_PATH, self.account_name, album_info["album_id"])
        self.temp_path_list.append(post_path)
        for image_url in album_info["image_url_list"]:
            self.main_thread_check()  # 检测主线程运行状态
            log.step(self.account_name + " 相册%s《%s》 开始下载第%s张图片 %s" % (album_info["album_id"], album_info["album_title"], image_index, image_url))

            file_path = os.path.join(post_path, "%s.jpg" % image_index)
            save_file_return = net.save_net_file(image_url, file_path)
            if save_file_return["status"] == 1:
                log.step(self.account_name + " 相册%s《%s》 第%s张图片下载成功" % (album_info["album_id"], album_info["album_title"], image_index))
                image_index += 1
            else:
                log.error(self.account_name + " 相册%s《%s》 第%s张图片 %s 下载失败，原因：%s" % (album_info["album_id"], album_info["album_title"],  image_index, image_url, robot.get_save_net_file_failed_reason(save_file_return["code"])))

        # 相册内图片全部下载完毕
        self.temp_path_list = []  # 临时目录设置清除
        self.total_image_count += image_index - 1  # 计数累加
        self.account_info[1] = album_info["album_id"]  # 设置存档记录

    def run(self):
        try:
            try:
                account_index_response = get_account_index_page(self.account_name)
            except robot.RobotException, e:
                log.error(self.account_name + " 主页解析失败，原因：%s" % e.message)
                raise

            # 获取所有可下载相册
            album_info_list = self.get_crawl_list(account_index_response["account_id"])
            log.step(self.account_name + " 需要下载的全部相册解析完毕，共%s个" % len(album_info_list))

            # 从最早的相册开始下载
            while len(album_info_list) > 0:
                self.main_thread_check()  # 检测主线程运行状态
                album_info = album_info_list.pop()
                log.step(self.account_name + " 开始解析相册%s" % album_info["album_id"])
                self.crawl_album(album_info)
                self.main_thread_check()  # 检测主线程运行状态
        except SystemExit, se:
            if se.code == 0:
                log.step(self.account_name + " 提前退出")
            else:
                log.error(self.account_name + " 异常退出")
            # 如果临时目录变量不为空，表示某个相册正在下载中，需要把下载了部分的内容给清理掉
            self.clean_temp_path()
        except Exception, e:
            log.error(self.account_name + " 未知异常")
            log.error(str(e) + "\n" + str(traceback.format_exc()))

        # 保存最后的信息
        with self.thread_lock:
            global TOTAL_IMAGE_COUNT
            tool.write_file("\t".join(self.account_info), NEW_SAVE_DATA_PATH)
            TOTAL_IMAGE_COUNT += self.total_image_count
            ACCOUNT_LIST.pop(self.account_name)
        log.step(self.account_name + " 下载完毕，总共获得%s张图片" % self.total_image_count)
        self.notify_main_thread()


if __name__ == "__main__":
    TuChong().main()
