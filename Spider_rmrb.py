from urllib.parse import urlencode
from requests.exceptions import RequestException
import requests
import json
from bs4 import BeautifulSoup
import re
import time
import random
import pymongo
import os
from hashlib import md5
from multiprocessing import Pool
from json.decoder import JSONDecodeError
from config import *

client = pymongo.MongoClient(MONGO_URL,connect=False)
db = client[MONGO_DB]

proxy = None

def get_proxy():
    try:
        response = requests.get(PROXY_POOL_URL)
        if response.status_code == 200:
            return response.content
        return None
    except ConnectionError:
        return None

def delete_proxy(proxy):
    requests.get("http://127.0.0.1:5010/delete/?proxy={}".format(proxy))

def get_html(url,headers,count = 1,):
    print('Crawling',url)
    print('Tring Count',count)
    max_count = 5
    global proxy
    if count>=max_count:
        print('Tried too much')
        delete_proxy(proxy)
        return None
    try:
        if proxy:
            response = requests.get(url,allow_redirects=False,headers=headers,proxies={"http": "http://{}".format(proxy)})
        else:
            response = requests.get(url,allow_redirects=False,headers=headers)
        if response.status_code == 200:
            return response.text
        if response.status_code == 302:
            print('302 error')
            proxy = get_proxy()
            if proxy:
                print('Using proxy: ',proxy)
                return get_html(url,headers)
            else:
                print('Get proxy failed!')
                return None
        if response.status_code == 429:
            print('429 error')
            time.sleep(random.randint(1800,3600))
            return get_html(url, headers)
    except ConnectionError as e:
        print('Error Occured',e.args)
        proxy = get_proxy()
        count += 1
        return get_html(url,headers,count)

def get_page_index(page,headers):
    data = {
            'qs': {"cds":[{"cdr":"AND","cds":[{"fld":"title","cdr":"OR","hlt":"true","vlr":"OR","val":'地震'},{"fld":"subTitle","cdr":"OR","hlt":"false","vlr":"OR","val":'地震'},{"fld":"introTitle","cdr":"OR","hlt":"false","vlr":"OR","val":'地震'},{"fld":"contentText","cdr":"OR","hlt":"true","vlr":"OR","val":'地震'}]}],"obs":[{"fld":"dataTime","drt":"DESC"}]},
            'tr': 'A',
            'ss': '1',
            'pageNo': page,
            'pageSize': '20',
            }
    url = 'http://data.people.com.cn/rmrb/s?' + urlencode(data)
    try:
        html = get_html(url,headers)
        return html
    except RequestException:
        print('打开索引页错误')
        time.sleep(random.randint(600,1800))
        return get_page_index(page,headers)
    
def parse_page_index(html):
    soup = BeautifulSoup(html,'lxml')
    hrefs = soup.select('h3 a')
    for h in hrefs:
        href = 'http://data.people.com.cn'+ h.attrs['href']
        yield href
            
def get_page_detail(url,headers):
    try:
        html = get_html(url,headers)
        return html
    except RequestException:
        print('打开详情页错误')
        return None
    
def parse_page_detail(html):
    try:
        soup = BeautifulSoup(html, 'lxml')
        titles = soup.select('.div_detail .title')
        if titles:
            for t in titles:
                title = t.get_text()
        else:
            title = None
        subtitles = soup.select('.div_detail .subtitle')
        if subtitles:
            for s in subtitles:
                subtitle = s.get_text()
        else:
            subtitle = None
        authors = soup.select('.div_detail .author')
        if authors:
            for a in authors:
                author = a.get_text()[4:][:-1]
        else:
            author = None
        dates = soup.select('.sha_left span')
        contents = soup.select('#FontZoom')
        for c in contents:
            content = c.get_text()
        return {
            '标题':title,
            '副题':subtitle,
            '作者':author,
            '日期':dates[0].text,
            '版面':dates[1].text,
            '类型':dates[2].text,
            '正文':content,
        }
    except IndexError:
        print('无法访问，可能未登录')
        pass

def save_to_mongo(data):
    if db[MONGO_TABLE].update({'标题': data['标题']}, {'$set': data}, True):
        print('Saved to Mongo', data)
    else:
        print('Saved to Mongo Failed', data['标题'])

def download_images(url):
    print('正在下载：',url)
    try:
        response = requests.get(url)
        if response.status_code == 200:
            save_images(response.content)
            return response.text
        return None
    except RequestException:
        print('请求图片下载错误')
        return None
    
def save_images(content):
    file_path = '{0}/{1}.{2}'.format(os.getcwd(),md5(content).hexdigest(),'png')
    if not os.path.exists(file_path):
        with open(file_path,'wb') as file:
            file.write(content)
            file.close
    
def main(page):
    headers = {
        'Cookie':COOKIE,
        'user-agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/70.0.3538.102 Safari/537.36'
        }
    html = get_page_index(page,headers)
    for url in parse_page_index(html):
        if url:
            html = get_page_detail(url,headers)
            if html:
                result = parse_page_detail(html)
                if result:
                    save_to_mongo(result)
                    time.sleep(random.randint(5,20))
                pass

if __name__ == '__main__':
    for i in range(1,1061):
        if i==200 or i==400 or i==600 or i==800:
            time.sleep(1800)
            print('Page:',i)
            main(i)
        else:
            print('Page:', i)
            main(i)
