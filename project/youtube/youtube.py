# -*- coding:UTF-8  -*-
"""
Youtube视频爬虫
https://www.youtube.com
@author: hikaru
email: hikaru870806@hotmail.com
如有问题或建议请联系
"""
from common import *
import json
import os
import re
import threading
import time
import traceback
import urllib

COOKIE_INFO = {}


# 获取用户首页
def get_one_page_video(account_id, token):
    # token = "4qmFsgJAEhhVQ2xNXzZHRU9razY2STFfWWJTUFFqSWcaJEVnWjJhV1JsYjNNZ0FEZ0JZQUZxQUhvQk1yZ0JBQSUzRCUzRA%3D%3D"
    result = {
        "video_id_list": [],  # 全部视频id
        "next_page_token": None,  # 下一页token
    }
    if token == "":
        # todo 更好的分辨方法
        if len(account_id) == 24:
            index_url = "https://www.youtube.com/channel/%s/videos" % account_id
        else:
            index_url = "https://www.youtube.com/user/%s/videos" % account_id
        index_response = net.http_request(index_url, method="GET")
        if index_response.status != net.HTTP_RETURN_CODE_SUCCEED:
            raise crawler.CrawlerException(crawler.request_failre(index_response.status))
        if index_response.data.find('<button id="a11y-skip-nav" class="skip-nav"') >= 0:
            log.step("首页访问出现跳转，再次访问")
            return get_one_page_video(account_id, token)
        script_data_html = tool.find_sub_string(index_response.data, 'window["ytInitialData"] =', ";\n").strip()
        if not script_data_html:
            raise crawler.CrawlerException("页面截取视频信息失败\n%s" % index_response.data)
        try:
            script_data = json.loads(script_data_html)
        except ValueError:
            raise crawler.CrawlerException("视频信息加载失败\n%s" % script_data_html)
        try:
            temp_data = script_data["contents"]["twoColumnBrowseResultsRenderer"]["tabs"][1]["tabRenderer"]["content"]["sectionListRenderer"]
            video_list_data = temp_data["contents"][0]["itemSectionRenderer"]["contents"][0]["gridRenderer"]
        except KeyError:
            raise crawler.CrawlerException("视频信息格式不正确\n%s" % script_data)
    else:
        query_url = "https://www.youtube.com/browse_ajax"
        query_data = {"ctoken": token}
        header_list = {
            "x-youtube-client-name": "1",
            "x-youtube-client-version": "2.20171207",
        }
        video_pagination_response = net.http_request(query_url, method="GET", fields=query_data, header_list=header_list, json_decode=True)
        if video_pagination_response.status != net.HTTP_RETURN_CODE_SUCCEED:
            raise crawler.CrawlerException(crawler.request_failre(video_pagination_response.status))
        try:
            video_list_data = video_pagination_response.json_data[1]["response"]["continuationContents"]["gridContinuation"]
        except KeyError:
            raise crawler.CrawlerException("视频信息格式不正确\n%s" % video_pagination_response.json_data)
    if not crawler.check_sub_key(("items",), video_list_data):
        raise crawler.CrawlerException("视频列表信息'items'字段不存在\n%s" % video_list_data)
    for item in video_list_data["items"]:
        if not crawler.check_sub_key(("gridVideoRenderer",), item):
            raise crawler.CrawlerException("视频信息'gridVideoRenderer'字段不存在\n%s" % item)
        if not crawler.check_sub_key(("videoId",), item["gridVideoRenderer"]):
            raise crawler.CrawlerException("视频信息'gridVideoRenderer'字段不存在\n%s" % item)
        result["video_id_list"].append(str(item["gridVideoRenderer"]["videoId"]))
    # 获取下一页token
    try:
        result["next_page_token"] = str(video_list_data["continuations"][0]["nextContinuationData"]["continuation"])
    except KeyError:
        pass
    return result


# 获取指定视频
def get_video_page(video_id):
    # https://www.youtube.com/watch?v=GCOSw4WSXqU
    video_play_url = "https://www.youtube.com/watch"
    query_data = {"v": video_id}
    # 强制使用英语

    video_play_response = net.http_request(video_play_url, method="GET", fields=query_data, cookies_list=COOKIE_INFO)
    result = {
        "video_time": None,  # 视频上传时间
        "video_url": None,  # 视频地址
    }
    # 获取视频地址
    if video_play_response.status != net.HTTP_RETURN_CODE_SUCCEED:
        raise crawler.CrawlerException(crawler.request_failre(video_play_response.status))
    video_info_string = tool.find_sub_string(video_play_response.data, "ytplayer.config = ", ";ytplayer.load = ").strip()
    if not video_info_string:
        raise crawler.CrawlerException("页面截取视频信息失败\n%s" % video_play_response.data)
    try:
        video_info_data = json.loads(video_info_string)
    except KeyError:
        raise crawler.CrawlerException("视频信息格式不正确\n%s" % video_info_string)
    if not crawler.check_sub_key(("args",), video_info_data):
        raise crawler.CrawlerException("视频信息'args'字段不存在\n%s" % video_info_data)
    if not crawler.check_sub_key(("url_encoded_fmt_stream_map",), video_info_data["args"]):
        raise crawler.CrawlerException("视频信息'url_encoded_fmt_stream_map'字段不存在\n%s" % video_info_data["args"])
    max_video_resolution = 0
    # signature生成步骤
    decrypt_function_step = []
    for sub_url_encoded_fmt_stream_map in video_info_data["args"]["url_encoded_fmt_stream_map"].split(","):
        video_resolution = video_url = signature = None
        is_skip = False
        for sub_param in sub_url_encoded_fmt_stream_map.split("&"):
            key, value = str(sub_param).split("=")
            if key == "type":  # 视频类型
                video_type = urllib.unquote(value)
                if video_type.find("video/mp4") == 0:
                    pass  # 只要mp4类型的
                elif video_type.find("video/webm") == 0 or video_type.find("video/3gpp") == 0:
                    is_skip = True  # 跳过
                    break
                else:
                    log.error("unknown video type " + video_type)
            elif key == "quality":  # 视频画质
                if value == "tiny":
                    video_resolution = 144
                elif value == "small":
                    video_resolution = 240
                elif value == "medium":
                    video_resolution = 360
                elif value == "large":
                    video_resolution = 480
                elif value[:2] == "hd" and crawler.is_integer(value[2:]):
                    video_resolution = int(value[2:])
                else:
                    video_resolution = 1
                    log.error("unknown video quality " + value)
            elif key == "url":
                video_url = urllib.unquote(value)
            elif key == "s":
                # 解析JS文件，获取对应的加密方法
                if len(decrypt_function_step) == 0:
                    js_file_name = tool.find_sub_string(video_play_response.data, 'src="/yts/jsbin/player-', '/base.js"')
                    js_file_url = "https://www.youtube.com/yts/jsbin/player-%s/base.js" % js_file_name
                    decrypt_function_step = get_decrypt_step(js_file_url)
                    log.trace("JS文件 %s 解析出的本地加密方法\n%s" % (js_file_url, decrypt_function_step))
                # 生成加密字符串
                signature = decrypt_signature(decrypt_function_step, value)
            elif key == "sig":
                signature = value
        if is_skip:
            continue
        if video_url is None or video_url is None:
            log.error("unknown video param" + video_info_string)
            continue
        if video_resolution > max_video_resolution:
            max_video_resolution = video_resolution
            if signature is not None:
                video_url += "&signature=" + str(signature)
            result["video_url"] = video_url
    if result["video_url"] is None:
        raise crawler.CrawlerException("视频地址解析错误\n%s" % video_info_string)
    # 获取视频发布时间
    video_time_string = tool.find_sub_string(video_play_response.data, '"dateText":{"simpleText":"', '"},').strip()
    if not video_time_string:
        video_time_string = tool.find_sub_string(video_play_response.data, '<strong class="watch-time-text">', '</strong>').strip()
    if not video_time_string:
        raise crawler.CrawlerException("页面截取视频发布时间错误\n%s" % video_play_response.data)
    # 英语
    if video_time_string.find("Published on") >= 0:
        video_time_string = video_time_string.replace("Published on", "").strip()
        try:
            video_time = time.strptime(video_time_string, "%b %d, %Y")
        except ValueError:
            raise crawler.CrawlerException("视频发布时间文本格式不正确\n%s" % video_time_string)
    # 中文
    elif video_time_string.find("发布") >= 0:
        video_time_string = video_time_string.replace("发布", "").strip()
        try:
            video_time = time.strptime(video_time_string, "%Y年%m月%d日")
        except ValueError:
            raise crawler.CrawlerException("视频发布时间文本格式不正确\n%s" % video_time_string)
    else:
        raise crawler.CrawlerException("未知语言的时间格式\n%s" % video_time_string)
    result["video_time"] = int(time.mktime(video_time))
    return result


# 部分版权视频需要的signature字段取值
# 每隔一段时间访问视频播放页面后会插入一个动态生成JS地址
# 里面包含3个子加密方法，但调用顺序、参数、次数每个JS文件中各不相
# 其中一个例子：https://youtube.com/yts/jsbin/player-vfl4OEYh9/en_US/base.js
# k.sig?f.set("signature",k.sig):k.s&&f.set("signature",SJ(k.s));
# SJ=function(a){a=a.split("");RJ.yF(a,48);RJ.It(a,31);RJ.yF(a,24);RJ.It(a,74);return a.join("")};
# var RJ={yF:function(a,b){var c=a[0];a[0]=a[b%a.length];a[b]=c},It:function(a){a.reverse()},yp:function(a,b){a.splice(0,b)}};
def get_decrypt_step(js_file_url):
    # 最终的调用子加密方法的顺序
    decrypt_function_step = []
    js_file_response = net.http_request(js_file_url, method="GET")
    if js_file_response.status != net.HTTP_RETURN_CODE_SUCCEED:
        raise crawler.CrawlerException("播放器JS文件 %s 访问失败，原因：%s" % (js_file_url, crawler.request_failre(js_file_response.status)))
    # 加密方法入口
    # k.sig?f.set("signature",k.sig):k.s&&f.set("signature",SJ(k.s));
    main_function_name = tool.find_sub_string(js_file_response.data, 'k.sig?f.set("signature",k.sig):k.s&&f.set("signature",', "(k.s));")
    if not main_function_name:
        raise crawler.CrawlerException("播放器JS文件 %s，加密方法名截取失败" % js_file_url)
    # 加密方法体（包含子加密方法的调用参数&顺序）
    # SJ=function(a){a=a.split("");RJ.yF(a,48);RJ.It(a,31);RJ.yF(a,24);RJ.It(a,74);return a.join("")};
    main_function_body = tool.find_sub_string(js_file_response.data, '%s=function(a){a=a.split("");' % main_function_name, 'return a.join("")};')
    if not main_function_body:
        raise crawler.CrawlerException("播放器JS文件 %s，加密方法体截取失败" % js_file_url)
    # 子加密方法所在的变量名字
    decrypt_function_var = None
    for sub_decrypt_step in main_function_body.split(";"):
        # RJ.yF(a,48); / RJ.It(a,31); / RJ.yF(a,24); / RJ.It(a,74);
        if not sub_decrypt_step:
            continue
        # (加密方法所在变量名，加密方法名，加密方法参数)
        sub_decrypt_step_find = re.findall("([\w\$_]*)\.(\w*)\(a,(\d*)\)", sub_decrypt_step)
        if len(sub_decrypt_step_find) != 1:
            raise crawler.CrawlerException("播放器JS文件 %s，加密步骤匹配失败\n%s" % (js_file_url, sub_decrypt_step))
        if decrypt_function_var is None:
            decrypt_function_var = sub_decrypt_step_find[0][0]
        elif decrypt_function_var != sub_decrypt_step_find[0][0]:
            raise crawler.CrawlerException("播放器JS文件 %s，加密子方法所在变量不一致\n%s" % (js_file_url, main_function_body))
        decrypt_function_step.append([sub_decrypt_step_find[0][1], sub_decrypt_step_find[0][2]])  # 方法名，参数
    # 子加密方法所在的变量内容
    # var RJ={yF:function(a,b){var c=a[0];a[0]=a[b%a.length];a[b]=c},It:function(a){a.reverse()},yp:function(a,b){a.splice(0,b)}};
    decrypt_function_var_body = tool.find_sub_string(js_file_response.data, "var %s={" % decrypt_function_var, "};")
    if not main_function_body:
        raise crawler.CrawlerException("播放器JS文件 %s，加密子方法截取失败" % js_file_url)
    # 所有子加密方法具体内容
    decrypt_function_body_list = decrypt_function_var_body.split(",\n")
    if len(decrypt_function_body_list) != 3:
        raise crawler.CrawlerException("播放器JS文件 %s，加密子方法已更新\n%s" % (js_file_url, decrypt_function_var_body))
    # JS文件里的方法名对应爬虫里的方法
    js_function_to_local_function = {}
    for decrypt_function_body in decrypt_function_body_list:
        decrypt_function_name = decrypt_function_body.split(":function")[0]
        if decrypt_function_body.find("a.reverse()") > 0:
            js_function_to_local_function[decrypt_function_name] = _decrypt_function2
        elif decrypt_function_body.find("a.splice(") > 0:
            js_function_to_local_function[decrypt_function_name] = _decrypt_function3
        else:
            js_function_to_local_function[decrypt_function_name] = _decrypt_function1
    # 子加密方法调用顺序中JS文件里的方法名，替换成爬虫里的方法名
    for step in decrypt_function_step:
        step[0] = js_function_to_local_function[step[0]]
    return decrypt_function_step


def decrypt_signature(decrypt_function_step, encrypt_string):
    encrypt_string_list = list(encrypt_string)
    for step in decrypt_function_step:
        step[0](encrypt_string_list, int(step[1]))
    return "".join(encrypt_string_list)


def _decrypt_function1(a, b):
    c = a[0]
    a[0] = a[b % len(a)]
    a[b] = c


def _decrypt_function2(a, b):
    a.reverse()


def _decrypt_function3(a, b):
    for i in range(b):
        a.pop(0)
    # return a[b:]


class Youtube(crawler.Crawler):
    def __init__(self):
        global COOKIE_INFO

        sys_config = {
            crawler.SYS_DOWNLOAD_VIDEO: True,
            crawler.SYS_SET_PROXY: True,
            crawler.SYS_GET_COOKIE: {".youtube.com": ()}
        }
        crawler.Crawler.__init__(self, sys_config)

        # 设置全局变量，供子线程调用
        COOKIE_INFO = self.cookie_value

        # 解析存档文件
        # account_id  video_count video_string_id  video_number_id
        self.account_list = crawler.read_save_data(self.save_data_path, 0, ["", "0", "", "0"])

    def main(self):
        # 循环下载每个id
        main_thread_count = threading.activeCount()
        for account_id in sorted(self.account_list.keys()):
            # 检查正在运行的线程数
            if threading.activeCount() >= self.thread_count + main_thread_count:
                self.wait_sub_thread()

            # 提前结束
            if not self.is_running():
                break

            # 开始下载
            thread = Download(self.account_list[account_id], self)
            thread.start()

            time.sleep(1)

        # 检查除主线程外的其他所有线程是不是全部结束了
        while threading.activeCount() > main_thread_count:
            self.wait_sub_thread()

        # 未完成的数据保存
        if len(self.account_list) > 0:
            tool.write_file(tool.list_to_string(self.account_list.values()), self.temp_save_data_path)

        # 重新排序保存存档文件
        crawler.rewrite_save_file(self.temp_save_data_path, self.save_data_path)

        log.step("全部下载完毕，耗时%s秒，共计视频%s个" % (self.get_run_time(), self.total_video_count))


class Download(crawler.DownloadThread):
    is_find = False

    def __init__(self, account_info, main_thread):
        crawler.DownloadThread.__init__(self, account_info, main_thread)
        self.account_id = self.account_info[0]
        if len(self.account_info) >= 5 and self.account_info[4]:
            self.account_name = self.account_info[4]
        else:
            self.account_name = self.account_info[0]
        log.step(self.account_name + " 开始")

    # 获取所有可下载视频
    def get_crawl_list(self):
        token = ""
        video_id_list = []
        # 是否有根据视频id找到上一次的记录
        if self.account_info[2] == "":
            self.is_find = True
        is_over = False
        # 获取全部还未下载过需要解析的相册
        while not is_over:
            self.main_thread_check()  # 检测主线程运行状态
            log.step(self.account_name + " 开始解析 %s 视频页" % token)

            # 获取一页视频
            try:
                blog_pagination_response = get_one_page_video(self.account_id, token)
            except crawler.CrawlerException, e:
                log.error(self.account_name + " 视频页（token：%s）解析失败，原因：%s" % (token, e.message))
                raise

            log.trace(self.account_name + " 视频页（token：%s）解析的全部日志：%s" % (token, blog_pagination_response["video_id_list"]))

            # 寻找这一页符合条件的日志
            for video_id in blog_pagination_response["video_id_list"]:
                # 检查是否达到存档记录
                if video_id != self.account_info[2]:
                    video_id_list.append(video_id)
                else:
                    is_over = True
                    self.is_find = True
                    break

            if not is_over:
                if blog_pagination_response["next_page_token"]:
                    # 设置下一页token
                    token = blog_pagination_response["next_page_token"]
                else:
                    is_over = True

        return video_id_list

    # 解析单个视频
    def crawl_video(self, video_id):
        video_index = int(self.account_info[1]) + 1
        # 获取指定视频信息
        try:
            video_response = get_video_page(video_id)
        except crawler.CrawlerException, e:
            log.error(self.account_name + " 第%s个视频%s解析失败，原因：%s" % (video_index, video_id, e.message))
            raise

        # 如果解析需要下载的视频时没有找到上次的记录，表示存档所在的视频已被删除，则判断数字id
        if not self.is_find:
            if video_response["video_time"] < int(self.account_info[3]):
                log.step(self.account_name + " 视频%s跳过" % video_id)
                return
            elif video_response["video_time"] == int(self.account_info[3]):
                log.error(self.account_name + " 第%s个视频%s与存档视频发布日期一致，无法过滤，再次下载" % (video_index, video_id))
            else:
                self.is_find = True

        self.main_thread_check()  # 检测主线程运行状态
        log.step(self.account_name + " 开始下载第%s个视频 %s" % (video_index, video_response["video_url"]))

        video_file_path = os.path.join(self.main_thread.video_download_path, self.account_name, "%04d.mp4" % video_index)
        save_file_return = net.save_net_file(video_response["video_url"], video_file_path)
        if save_file_return["status"] == 1:
            # 设置临时目录
            log.step(self.account_name + " 第%s个视频下载成功" % video_index)
        else:
            log.error(self.account_name + " 第%s个视频（%s） %s 下载失败，原因：%s" % (video_index, video_id, video_response["video_url"], crawler.download_failre(save_file_return["code"])))

        # 媒体内图片和视频全部下载完毕
        self.total_video_count += 1  # 计数累加
        self.account_info[1] = str(video_index)  # 设置存档记录
        self.account_info[2] = video_id  # 设置存档记录
        self.account_info[3] = str(video_response["video_time"])  # 设置存档记录

    def run(self):
        try:
            # 获取所有可下载视频
            video_id_list = self.get_crawl_list()
            log.step(self.account_name + " 需要下载的全部视频解析完毕，共%s个" % len(video_id_list))
            if not self.is_find:
                log.step(self.account_name + " 存档所在视频已删除，需要在下载时进行过滤")

            # 从最早的视频开始下载
            while len(video_id_list) > 0:
                video_id = video_id_list.pop()
                log.step(self.account_name + " 开始解析第%s个视频%s" % (int(self.account_info[1]) + 1, video_id))
                self.crawl_video(video_id)
                self.main_thread_check()  # 检测主线程运行状态
        except SystemExit, se:
            if se.code == 0:
                log.step(self.account_name + " 提前退出")
            else:
                log.error(self.account_name + " 异常退出")
        except Exception, e:
            log.error(self.account_name + " 未知异常")
            log.error(str(e) + "\n" + str(traceback.format_exc()))

        # 保存最后的信息
        with self.thread_lock:
            tool.write_file("\t".join(self.account_info), self.main_thread.temp_save_data_path)
            self.main_thread.total_video_count += self.total_video_count
            self.main_thread.account_list.pop(self.account_id)
        log.step(self.account_name + " 下载完毕，总共获得%s个视频" % self.total_video_count)
        self.notify_main_thread()


if __name__ == "__main__":
    Youtube().main()
