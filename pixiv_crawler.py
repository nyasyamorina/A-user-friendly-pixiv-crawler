""" 一个比较人性化的pixiv爬虫包       (内部代码并不人性化)
 内部包装了一些使用urllib实现的对pixiv特异化操作, 可直接获取pixiv数据

 示例:  (根据pid下载一张图片)
    from pixiv_crawler import pixiv_tool
    page = pixiv_tool.get_artworksPage_from_pid(pid=82693472)
    img = pixiv_tool.get_img_from_artworksPage(page.decode())
    img.save(save_dir='./pixiv_download')
 或
    from pixiv_crawler import pixiv_image
    pixiv_image(pid=82693472).save(save_dir='./pixiv_download')

 详细帮助请善用 dir() & help() """


import asyncio
import json
import warnings
from urllib import request
from urllib.error import HTTPError
from typing import Any, Dict, List, Union

artworks_url = 'https://www.pixiv.net/artworks/{pid}'
original_url = 'https://i.pximg.net/img-original/img/{year}/{mon}/{day}/{hour}/{min}/{sec}/{pid}_p{page}.{imgtype}'

not_image = 'this is not a image.'


class pixiv_ranking_url:
    """ 用于快速从日期等参数获得排行榜链接,
        推荐直接使用 pixiv_ranking_url.format 获得."""
    _url = 'https://www.pixiv.net/ranking.php?mode={mode}{date}'
    _date = '&date={year}{mon:02d}{day:02d}'

    def __init__(self, year: int = None, mon: int = None, day: int = None, mode: str = 'daily', r18: bool = False):
        """ year,mon,day 需要同时给出或不给出. 不给出则忽略日期
            当r18=False时, mode支持以下关键字: ('daily', 'weekly', 'monthly', 'rookie', 'original', 'male', 'female'),
            否则只支持以下关键字: ('daily', 'weekly', 'male', 'female') """
        self.year = year
        self.mon = mon
        self.day = day
        self.mode = mode
        self.r18 = r18

    def __str__(self) -> str:
        assert self.mode in ('daily', 'weekly', 'monthly', 'rookie', 'original', 'male', 'female')
        if self.r18:
            assert self.mode in ('daily', 'weekly', 'male', 'female')
        _a = self.year is None
        _b = self.mon is None
        _c = self.day is None
        assert not ((_a ^ _b) and (_b ^ _c) and (_a ^ _c)), 'year,mon,day 需要同时给出.'

        date = self._date.format(year=self.year, mon=self.mon, day=self.day) if not _a else ''
        mode = self.mode + '_r18' if self.r18 else self.mode
        return self._url.format(mode=mode, date=date)

    @classmethod
    def format(cls, *args, **kwargs) -> str:
        """ 把 pixiv_ranking_url 伪装成str, 输入参数请参考__init__ """
        return cls(*args, **kwargs).__str__()


def _download(url: str, headers: Dict[str, str] = None) -> bytes:
    """ 一个使用 urllib 下载网页的定型文方法, 不推荐使用 """
    with request.urlopen(request.Request(url, headers=headers)) as response:
        html_page = response.read()
    return html_page


def _reset_oriPage(original: str) -> str:
    """ 把原图链接里的页码设为{page}, 不推荐使用 """
    if original == not_image:
        return original
    p = original.rfind('/') + 1
    end = original[p:]
    original = original[:p]
    end0, end1 = end.split('_p')
    p = end1.find('_')
    if p == -1:
        p = end1.find('.')
    return original + end0 + '_p{page}' + end1[p:]


class pixiv_image:
    """ 储存 pixiv 图片(或者叫illust?)的类
        可以直接传入pid或者原图链接初始化这个类

        方法:
            pixiv_image.data     获取图片的二进制数据
            pixiv_image.save()   把图片保存到目标文件夹"""

    def __init__(self, pid: int = None, original: str = None, *_, **kwargs):
        """ pid 和 original(原图链接) 必须至少传入其中一个,
            使用位置参数传入时, pid 和 original 可以互换位置
            其他图片信息(见下), 都必须为关键字参数传入 (可选)

            其他图片信息:
                title         str   标题
                size     (int,int)  大小    格式:(height, width)
                author        str   作者名字
                author_id     int   作者 id
                pages         int   页数
                description   str   简介"""
        assert (pid is not None) or (original is not None), 'pid或原图连接必须给出其中一个'
        if isinstance(pid, str):
            try:
                pid = int(pid)
            except ValueError:
                original, pid = pid, original

        self._pid = pid
        self._original = _reset_oriPage(original) if original is not None else None
        self.title = kwargs.get('title')
        self.size = kwargs.get('size')
        self.author = kwargs.get('author')
        self.author_id = kwargs.get('author_id')
        self.tags = kwargs.get('tags')
        self.pages = kwargs.get('pages', 1)
        self.description = kwargs.get('description')
        self._data = None
        self._typecheck = False
        # 因为从 get_oriImgUrl_from_otherSizeUrl 返回的链接后缀可能不正确
        # 这里使用了 _typecheck 标记判断后缀是否正确
        # True 为链接后缀已经正确, 否则为 False

    def update_info(self, *_, **img_info) -> None:
        """ 用于更新图片信息的方法, 包括 pid 和 original """
        self._pid = img_info.get('pid', self._pid)
        self._original = img_info.get('original', self._original)
        self.title = img_info.get('title', self.title)
        self.size = img_info.get('szie', self.size)
        self.author = img_info.get('author', self.author)
        self.author_id = img_info.get('author_id', self.author_id)
        self.tags = img_info.get('tags', self.tags)
        self.pages = img_info.get('pages', self.pages)
        self.description = img_info.get('description', self.description)
        self._original = _reset_oriPage(self._original) if self._original is not None else None

    def _init_use_original(self) -> None:
        """ 从自身的 original 获取并更新自身的 pid, 不推荐使用
            如果 original 不符合格式, 如 None 或 not_image, 则会抛出异常[TypeError] """
        if self._original is None or self._original == not_image:
            raise TypeError('请提供正确的 original.')
        p = self._original.rfind('/') + 1
        self._pid = int(self._original[p:].split('_p')[0])

    def _init_use_pid(self) -> None:
        """ 从自身的 pid 获取并更新自身的 original 及其他图片信息, 不推荐使用
            注意: 这个方法实质上是请求相应的artworks页面并解析, 需要使用网络 """
        html_page = pixiv_tool.get_artworksPage_from_pid(self._pid)
        img_info = pixiv_tool._get_imgInfo_from_artworksPage(html_page.decode())
        self.update_info(**img_info)
        self._typecheck = True

    async def download_data(self, executor=None) -> None:
        """ 从自身的 original 和 pages(可选) 下载图片数据到自身的 data
            注意: 这个方法为异步函数, 当下载数据量比较大时推荐在外部调用这个方法,
                  不熟悉异步操作的可以直接使用 pixiv_image.data 获取数据. """
        if self._original == not_image:
            return

        headers = dict(referer=artworks_url.format(pid=self.pid), **pixiv_tool.headers)
        url = self.original.format(page=0)

        if not self._typecheck:
            try:
                # 一般来说, 原图链接除了后缀的其他信息没错的话,
                # 当请求时404了, 把后缀换了就正确了.
                #
                # 但是还有一种我设想的情况: 画师在上传多图时格式不一致的话,
                # 这个时候就暂时需要自己实现了. (如果遇到了请联系我reporte一下)
                data = _download(url, headers)
            except HTTPError as http_error:
                if http_error.code == 404:
                    if self._original.endswith('jpg'):
                        self._original = self._original.replace('jpg', 'png')
                    else:
                        self._original = self._original.replace('png', 'jpg')
                else:
                    raise
                data = _download(self._original.format(page=0), headers)
            self._typecheck = True
            if self.pages == 1 or self.pages is None:
                self._data = data

            else:
                loop = asyncio.get_event_loop()
                coroutine = [loop.run_in_executor(executor, _download,
                                                  self.original.format(page=page), headers) for page in
                             range(1, self.pages)]
                datas = await asyncio.gather(*coroutine)
                self._data = [data, *datas]

        elif self.pages == 1 or self.pages is None:
            self._data = _download(self.original.format(page=0), headers)

        else:
            loop = asyncio.get_event_loop()
            coroutine = [loop.run_in_executor(executor, _download,
                                              self.original.format(page=page), headers) for page in range(self.pages)]
            datas = await asyncio.gather(*coroutine)
            if self.pages == 1:
                self._data = datas[0]
            else:
                self._data = datas

    @property
    def pid(self) -> int:
        if self._pid is None:
            self._init_use_original()
        return self._pid

    @property
    def original(self) -> str:
        """ 如果不需要一定获取原图连接(比如说初始化时没给出), 则可以使用 pixiv_image._original """
        if self._original is None:
            self._init_use_pid()
        return self._original

    @property
    def data(self) -> Union[bytes, List[bytes]]:
        """ 获取图片的数据, 当使用这个方法时会自动调用 download_data
            单图会返回二进制流 (或者未指定 pages )
            多图则会返回元素为二进制的列表, 并且排列顺序为页码顺序

            如果不需要一定获取图片数据, 则可以使用 pixiv_image._data """
        if self._data is None:
            asyncio.run(self.download_data())
        return self._data

    def save(self, save_dir: str) -> None:
        """ 保存图片(或多图)到指定文件夹, 文件夹不存在时会自动创建

            如果是单图的话, 会储存为 "{save_dir}/{pid}.jpg"
            否则会储存为 "{save_dir}/{pid}/{page}.jpg"
            保存示例:
            save_dit -- pid -------- 0.jpg    (多图)
                      |           |- 1.jpg
                      |- pid.png              (单图)"""
        import os
        img_type = 'jpg' if self.original.endswith('jpg') else 'png'
        if self.pages == 1:
            os.makedirs(save_dir, exist_ok=True)
            with open(f'{save_dir}/{self.pid}.{img_type}', 'wb') as save_file:
                save_file.write(self.data)

        else:
            os.makedirs(f'{save_dir}/{self.pid}', exist_ok=True)
            for page, data in enumerate(self.data):
                with open(f'{save_dir}/{self.pid}/{page}.{img_type}', 'wb') as save_file:
                    save_file.write(data)

    def __str__(self) -> str:
        img_info = f'pid={self._pid}' if self._pid is not None else f'original={self._original}'
        return f'pixiv_image[{img_info}]'


class pixiv_tool:
    """ 一些用得上的pixiv方法:
            get_artworksPage_from_pid: 使用pid获得图片的网页数据
            get_rankingPage_from_date: 指定日期获得排行榜的网页数据
            get_img_from_artworksPage: 从图片的网页获得 pixiv_image
            get_imgs_from_rankingPage: 从排行榜的网页数据获得关于 pixiv_image 的字典
            get_oriImgUrl_from_otherSizeUrl: 从其他尺寸的图片链接获得原图链接 """

    headers = {'user-agent': ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
                              'Chrome/83.0.4103.116 Safari/537.36')
               }

    @classmethod
    def get_artworksPage_from_pid(cls, pid: int) -> bytes:
        """ 使用pid获得图片的网页数据
            注意: 返回的为二进制流, 需要经过decode才可以get_img... """
        url = artworks_url.format(pid=pid)
        headers = cls.headers
        return _download(url, headers)

    @classmethod
    def get_rankingPage_from_date(cls, *args, **kwargs) -> bytes:
        """ 从日期获得排行榜的页面数据, 传入参数请参考 pixiv_ranking_url.__init__
            注意: 返回的为二进制流, 需要经过解码才可以get_img... """
        if 'cookie' not in cls.headers.keys():
            warnings.warn('或者你可能需要提供cookie给 pixiv_houhou.headers ', RuntimeWarning)

        url = pixiv_ranking_url.format(*args, **kwargs)
        headers = cls.headers
        return _download(url, headers)

    @classmethod
    def _get_imgInfo_from_artworksPage(cls, html_page: str) -> Dict[str, Any]:
        """ 解析(暴力匹配)图片的网页数据获得图片信息, 不推荐使用
            注意: 传入为字符串, 对使用pixiv_tool get来的网页需要经过解码 """
        html_page = html_page.replace('\r', '').replace('\n', '')
        before_json_info = '<meta name="preload-data" id="meta-preload-data" content=\''

        json_info_start = html_page.find(before_json_info) + len(before_json_info)
        json_info_end = html_page[json_info_start:].rfind('}}}\'>') + json_info_start + 3

        json_info = json.loads(html_page[json_info_start:json_info_end])
        pid = list(json_info['illust'].keys())[0]
        userid = list(json_info['user'].keys())[0]
        img_info = dict()

        illust_dict = json_info['illust'][pid]
        img_info['title'] = illust_dict['illustTitle']
        img_info['size'] = (illust_dict['width'], illust_dict['height'])
        img_info['author'] = json_info['user'][userid]['name']
        img_info['pid'] = pid
        img_info['author_id'] = userid
        img_info['tags'] = [tag['tag'] for tag in illust_dict['tags']['tags']]
        img_info['original'] = illust_dict['urls']['original']
        img_info['pages'] = illust_dict['pageCount']
        img_info['description'] = illust_dict['illustComment'].replace('&lt;br /&gt;', '\n')

        return img_info

    @classmethod
    def get_img_from_artworksPage(cls, html_page: str) -> pixiv_image:
        """ 解析图片的网页数据获得图片 """
        _image = pixiv_image(**cls._get_imgInfo_from_artworksPage(html_page))
        _image._typecheck = True
        return _image

    @classmethod
    def _get_imgsInfo_from_rankingPage(cls, html_page: str) -> Dict[str, Dict[str, Any]]:
        """ 解析(暴力匹配)排行榜的网页数据获得图片s的信息, 不推荐使用
            返回的为一个字典, 键值为图片在排行榜的排名(int)
            注意: 传入为字符串, 对使用pixiv_tool get来的网页需要经过解码 """
        html_page = html_page.replace('\r', '').replace('\n', '')
        split_key = '<section id="'
        info_keys = {
                'title':     'data-title="{}"',
                'author':    'data-user-name="{}"',
                'pid':       'data-id="{}"',
                'thumb':     'data-src="{}"',
                'tags':      'data-tags="{}"',
                'author_id': 'data-user-id="{}"'}

        html_list = html_page.split(split_key)[1:]
        html_list[-1] = html_list[-1][:html_list[-1].find('</section>')]
        imgs_info = dict()

        for html_string in html_list:

            p = html_string.find('"')
            rank = html_string[:p]
            imgs_info[rank] = dict()

            for key, keyword in info_keys.items():
                start, end = keyword.split('{}')
                html_string = html_string[html_string.find(start) + len(start):]
                p = html_string.find(end)
                imgs_info[rank][key] = html_string[:p]

            p = html_string.find('<span>')
            if p != -1:
                html_string = html_string[p + 6:]
                p = html_string.find('</span>')
                imgs_info[rank]['pages'] = int(html_string[:p])
            else:
                imgs_info[rank]['pages'] = 1

            imgs_info[rank]['pid'] = int(imgs_info[rank]['pid'])
            imgs_info[rank]['tags'] = imgs_info[rank]['tags'].split(' ')
        return imgs_info

    @classmethod
    def get_imgs_from_rankingPage(cls, html_page: str) -> Dict[str, pixiv_image]:
        """ 解析排行榜的网页数据据获得图片s
            返回的为一个字典, 键值为图片在排行榜的排名(int) """
        imgs = dict()
        for rank, info in cls._get_imgsInfo_from_rankingPage(html_page).items():
            imgs[rank] = pixiv_image(**info)
            imgs[rank].update_info(original=cls.get_oriImgUrl_from_otherSizeUrl(info['thumb']))
        return imgs

    @classmethod
    def get_oriImgUrl_from_otherSizeUrl(cls, url: str) -> str:
        """ 从其他尺寸的图片链接获得原图链接
            注意:
                1) 返回链接的后缀基本上是jpg, 但是原图有可能是png, 直接拿去下载可能会404
                   这个问题在pixiv_image里自行解决了
                2) 如果原图是一个视频, 则会返回 not_image """
        words = url.split('/')
        p = 7 if words[3] == 'c' else 5
        time_format = ('year', 'mon', 'day', 'hour', 'min', 'sec')
        time = {x: y for x, y in zip(time_format, words[p:p + len(time_format)])}

        words = words[-1].split('_')
        if len(words) != 3:
            warnings.warn('pixiv里的视频无法获取原图连接', RuntimeWarning)
            return not_image

        pid = int(words[0])
        page = int(words[1][1:])
        imgtype = words[2].split('.')[1]

        return original_url.format(**time, pid=pid, page=page, imgtype=imgtype)

    @classmethod
    def set_cookie(cls, cookie: str) -> None:
        """ 设置 headers 里的 cookie, 则可以帮助你获取更多的数据, 比如 r18.
            但是因为位置的原因, 设置了cookie还是有些数据不能获取. (努力抓包中...)"""
        cls.headers['cookie'] = cookie
