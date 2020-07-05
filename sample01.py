""" 一个爬取当前排行榜的例子 """
from urllib import request
from urllib.error import HTTPError

from pixiv_crawler import pixiv_tool


request.install_opener(request.build_opener(request.ProxyHandler(
        dict(http='http://127.0.0.1:10809', https='https://127.0.0.1:10809'))))

pixiv_tool.set_cookie(' your cookie. ')

page = pixiv_tool.get_rankingPage_from_date()
imgs = pixiv_tool.get_imgs_from_rankingPage(page.decode())

for rank, img in imgs.items():
    try:
        img.save(save_dir='./pixiv_download')
    except HTTPError as error:
        print(img.original, error)
