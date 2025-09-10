# -*- coding: utf-8 -*-

import requests
import hmac
import hashlib
import base64
import time
import json
import logging
import os
import uuid
import subprocess
from typing import List, Dict, Any, Tuple

# ====================================================================================
# [설정] 아래에 입력된 API 키와 ID를 확인하세요.
# ====================================================================================
# 쿠팡 파트너스 API 인증 정보
COUPANG_ACCESS_KEY = "d9ba9b35-1be8-46a3-b5eb-ef1add119ac8"
COUPANG_SECRET_KEY = "0912f82b517c3b406e89f66829449181d61d39ad"

# 구글 Gemini API 키
GEMINI_API_KEY = "AIzaSyDWKHjLNjupbX-Lb0X5KqaN8OTljwsOT7E"
GEMINI_API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-05-20:generateContent?key={GEMINI_API_KEY}"

# 상품 게시 기록 파일
POSTED_PRODUCTS_FILE = "posted_products.json"

# GitHub 저장소 설정 (로컬 저장소 경로와 원격 URL을 입력하세요)
# Codespaces 환경에 맞게 로컬 경로를 동적으로 설정합니다.
GITHUB_REPO_PATH = os.getcwd()
GITHUB_REPO_URL = "https://github.com/afallfree-oss/as.git"
GITHUB_BRANCH = "main"

# 로깅 설정
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# ====================================================================================
# 함수: 쿠팡 파트너스 API 연동
# ====================================================================================
def generate_hmac(method: str, url: str, secret_key: str, access_key: str, datetime_gmt: str, body: str = "") -> str:
    """ 쿠팡 파트너스 API를 위한 HMAC 서명을 생성합니다. """
    path, *query = url.split("?")
    message = datetime_gmt + method + path + (query[0] if query else "") + body
    
    signature = hmac.new(
        bytes(secret_key, "utf-8"),
        message.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()

    return f"CEA algorithm=HmacSHA256, access-key={access_key}, signed-date={datetime_gmt}, signature={signature}"

def get_products_by_category(category_id: int, keyword: str, limit: int = 10, min_price: int = 50000, max_price: int = 1000000) -> List[Dict[str, Any]]:
    """
    쿠팡 파트너스 검색 API를 통해 특정 카테고리와 키워드로 상품을 가져와 가격대를 필터링합니다.
    """
    request_method = "GET"
    DOMAIN = "https://api-gateway.coupang.com"
    api_uri = "/v2/providers/affiliate_open_api/apis/openapi/products/search"
    query_params = {
        "categoryId": category_id,
        "keyword": keyword,  # 키워드 추가
        "limit": limit
    }

    datetime_gmt = time.strftime('%y%m%d', time.gmtime()) + 'T' + time.strftime('%H%M%S', time.gmtime()) + 'Z'
    full_url = f"{DOMAIN}{api_uri}"
    query_string = requests.Request(request_method, url=full_url, params=query_params).prepare().url.split('?', 1)[1]
    full_url_with_query = f"{api_uri}?{query_string}"
    authorization = generate_hmac(request_method, full_url_with_query, COUPANG_SECRET_KEY, COUPANG_ACCESS_KEY, datetime_gmt)
    
    headers = {
        'Accept': 'application/json',
        'Authorization': authorization,
        'X-Requested-With': 'XMLHttpRequest',
        'X-Coupang-Date': datetime_gmt
    }

    try:
        response = requests.get(f"{DOMAIN}{full_url_with_query}", headers=headers)
        if response.status_code == 404:
            logging.error("쿠팡 API 요청 중 404 Not Found 오류 발생.")
            return []
            
        response.raise_for_status() 
        response_data = response.json()

        rCode = response_data.get('rCode')
        if rCode and rCode != '0':
            logging.error(f"쿠팡 API에서 오류 코드 반환: {rCode}, 메시지: {response_data.get('rMessage', '메시지 없음')}")
            return []

        products = response_data.get('data', {}).get('productData', [])
        
        product_list = []
        if products and isinstance(products, list):
            for p in products:
                if isinstance(p, dict):
                    # 가격 필터링 로직 추가
                    price = p.get('productPrice', 0)
                    if min_price <= price <= max_price:
                        product_list.append({
                            "name": p.get("productName", ""),
                            "image": p.get("productImage", ""),
                            "url": p.get("productUrl", ""),
                            "price": price
                        })
        return product_list
    
    except requests.exceptions.RequestException as e:
        logging.error(f"쿠팡 API 요청 중 오류 발생: {e}")
        return []
    except json.JSONDecodeError:
        logging.error("API 응답이 유효한 JSON 형식이 아닙니다.")
        return []
        
def generate_persuasive_article(product_name: str) -> str:
    """ Gemini API를 호출하여 특정 상품에 대한 1500자 분량의 설득력 있는 블로그 글을 생성합니다. """
    prompt = (
        f"'{product_name}'에 대한 구매를 유도하는 블로그 글을 1500자 내외의 '해요체'로 작성해 주세요. "
        "글은 다음과 같은 순서로 진행해 주세요: "
        "1. 시선을 끄는 서론: 독자가 현재 겪고 있을 문제나 필요성을 공감하며, 이 상품이 어떻게 해결책이 될 수 있는지 호기심을 유발하는 문장으로 시작해 주세요. "
        "2. 구체적인 본론: 상품의 주요 기능, 디자인, 사용 시의 장점을 3-4개 상세 문단으로 나누어 설명해 주세요. 이 상품이 왜 특별하고 다른 상품들과 다른지 강조해 주세요. "
        "3. 결론 및 구매 유도: 이 상품을 구매했을 때 얻게 될 긍정적인 변화와 가치를 다시 한번 요약하고, 마지막으로 행동을 유도하는 강력한 문장으로 마무리해 주세요. "
        "4. 핵심 요약: 본론의 내용을 3가지 핵심 장점으로 요약하여 별도로 제공해 주세요. 이 요약은 나중에 강조하여 보여줄 것입니다. "
        "최대한 감성적이고 설득력 있는 문체로 작성해 주시고, 서론, 본론, 결론, 핵심 요약과 같은 제목은 사용하지 말아주세요. "
    )
    payload = {
        "contents": [
            {
                "parts": [
                    {
                        "text": prompt
                    }
                ]
            }
        ]
    }
    
    try:
        response = requests.post(GEMINI_API_URL, json=payload, timeout=60)
        response.raise_for_status()
        
        candidates = response.json().get('candidates', [])
        if not candidates:
            logging.warning(f"'{product_name}'에 대한 Gemini API 응답에서 후보를 찾을 수 없습니다.")
            return "상품 설명을 생성하는 데 실패했습니다. 잠시 후 다시 시도해 주세요."
        
        generated_text = candidates[0].get('content', {}).get('parts', [{}])[0].get('text', '')
        return generated_text.strip()
    
    except requests.exceptions.RequestException as e:
        logging.error(f"Gemini API 요청 중 오류 발생: {e}")
        return "상품 설명을 생성하는 데 실패했습니다. 잠시 후 다시 시도해 주세요."
        
def generate_full_blog_content(product: Dict[str, str], article_content: str) -> str:
    """ 하나의 블로그 게시물을 구성하는 마크다운(Markdown)을 생성합니다. """
    if not product:
        return ""

    name = product.get('name', '상품명 없음')
    image_url = product.get('image', '')
    product_url = product.get('url', '#')
    
    try:
        summary_start_index = article_content.rfind('핵심 요약')
        if summary_start_index != -1:
            main_article = article_content[:summary_start_index].strip()
            summary_list_text = article_content[summary_start_index:].replace('핵심 요약', '').strip()
            summary_list_items = [f"- {item.strip()}" for item in summary_list_text.split('\n') if item.strip()]
            summary_markdown = f"""
> ### 이 상품을 선택해야 하는 이유
> {'\n> '.join(summary_list_items)}
"""
        else:
            main_article = article_content
            summary_markdown = ""
    except Exception as e:
        logging.error(f"핵심 요약 추출 중 오류 발생: {e}")
        main_article = article_content
        summary_markdown = ""

    markdown_content = f"""---
title: "[광고] 인생 아이템! '{name}'을(를) 만나보세요."
date: {time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime())}
---
### 상품 이미지
[![{name} 이미지]({image_url})]({product_url})

{main_article}

{summary_markdown}

<br>

<div align="center">
  <p>이 상품이 궁금하시다면 아래 버튼을 눌러 확인해 보세요!</p>
  <a href="{product_url}" target="_blank">
    <img src="https://img.shields.io/badge/지금 바로 구매하기-FF5722?style=for-the-badge&logo=coupa&logoColor=white" alt="구매하기 버튼">
  </a>
</div>

이 포스팅은 쿠팡 파트너스 활동의 일환으로, 이에 따른 일정액의 수수료를 제공받습니다.
"""
    return markdown_content

def create_index_file(posts_list: List[Dict[str, Any]]):
    """ 블로그 게시물 목록을 보여주는 index.md 파일을 생성합니다. """
    index_content = """---
layout: default
title: '나만의 쿠팡 파트너스 블로그'
---
## 최신 상품 리뷰

{% for post in site.posts %}
  <div class="post-item">
    <h3><a href="{{ site.baseurl }}{{ post.url }}">{{ post.title }}</a></h3>
    <p>{{ post.excerpt | strip_html | strip_newlines | truncate: 200 }}</p>
    <a href="{{ site.baseurl }}{{ post.url }}">더 읽어보기</a>
  </div>
{% endfor %}
"""
    with open("index.md", "w", encoding="utf-8") as f:
        f.write(index_content)
    logging.info("메인 페이지(index.md)가 없어 새로 생성합니다.")
        
def post_to_github(title: str, content: str):
    """
    새로운 마크다운 파일을 생성하고 Git을 사용해 GitHub에 푸시합니다.
    파일 이름 길이를 제한하여 오류를 방지합니다.
    """
    if not os.path.exists(GITHUB_REPO_PATH):
        logging.error(f"지정된 Git 저장소 경로가 없습니다: {GITHUB_REPO_PATH}")
        return

    os.chdir(GITHUB_REPO_PATH)
    
    try:
        logging.info("Git 변경사항을 커밋하기 전에 최신 내용을 가져오는 중...")
        subprocess.run(["git", "pull", "origin", "main"], check=True)
    except subprocess.CalledProcessError as e:
        logging.error(f"Git 명령 실행 중 오류 발생: {e}")
        logging.error("깃허브 계정에 SSH 키가 등록되어 있거나, 토큰 권한 설정이 올바른지 확인해주세요.")
        return

    # 마크다운 파일 이름 생성
    # 파일명 길이 제한 및 충돌 방지를 위해 고유 ID 추가
    slug = title.replace('[광고]', '').replace('인생 아이템!', '').replace('을(를) 만나보세요.', '').strip().replace(' ', '-').replace('/', '-').replace('(', '').replace(')', '').replace(',', '').replace('+', '-')
    unique_id = uuid.uuid4().hex[:8] # 짧은 고유 ID 생성
    slug_truncated = slug[:50] # 슬러그를 50자로 자르기
    file_name = f"_posts/{time.strftime('%Y-%m-%d', time.gmtime())}-{slug_truncated}-{unique_id}.md"
    
    os.makedirs(os.path.dirname(file_name), exist_ok=True)
    
    with open(file_name, "w", encoding="utf-8") as f:
        f.write(content)

    # index.md 파일이 없으면 새로 생성
    if not os.path.exists("index.md"):
        create_index_file([])

    try:
        logging.info("Git 변경사항을 커밋하고 푸시하는 중...")
        subprocess.run(["git", "add", "."], check=True)
        commit_message = f"Add new post: {title}"
        subprocess.run(["git", "commit", "-m", commit_message], check=True)
        subprocess.run(["git", "push", "origin", GITHUB_BRANCH], check=True)
        
        logging.info("✅ 깃허브에 성공적으로 글이 게시되었습니다!")
        logging.info(f"   게시된 파일: {file_name}")
    except subprocess.CalledProcessError as e:
        logging.error(f"Git 명령 실행 중 오류 발생: {e}")
        logging.error("깃허브 계정에 SSH 키가 등록되어 있거나, 토큰 권한 설정이 올바른지 확인해주세요.")
    except Exception as e:
        logging.error(f"깃허브에 푸시하는 중 오류 발생: {e}")

# ====================================================================================
# 함수: 게시된 상품 기록 관리
# ====================================================================================
def load_posted_products() -> List[str]:
    """ 게시된 상품 목록을 파일에서 불러옵니다. """
    if os.path.exists(POSTED_PRODUCTS_FILE):
        with open(POSTED_PRODUCTS_FILE, 'r', encoding='utf-8') as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                logging.warning("게시 기록 파일이 손상되었거나 형식이 올바르지 않습니다. 새 파일을 생성합니다.")
                return []
    return []

def save_posted_products(products: List[str]):
    """ 게시된 상품 목록을 파일에 저장합니다. """
    with open(POSTED_PRODUCTS_FILE, 'w', encoding='utf-8') as f:
        json.dump(products, f, ensure_ascii=False, indent=4)
        
# ====================================================================================
# 메인 함수: 전체 프로세스 실행
# ====================================================================================
if __name__ == "__main__":
    logging.info("🚀 쿠팡 파트너스 자동 블로그 포스팅 시스템 (GitHub Pages)을 시작합니다...")
    
    # 1. 이전 게시 기록 로드
    posted_products = load_posted_products()
    logging.info(f"이전에 게시된 상품 수: {len(posted_products)}개")

    # 포스팅할 상품 카테고리 ID 및 이름 목록
    categories = {
        1001: "여성패션", 1002: "남성패션", 1010: "뷰티", 1011: "출산/유아동",
        1012: "식품", 1013: "주방용품", 1014: "생활용품", 1015: "홈인테리어",
        1016: "가전디지털", 1017: "스포츠/레저", 1018: "자동차용품", 1019: "도서/음반/DVD",
        1020: "완구/취미", 1021: "문구/오피스", 1024: "헬스/건강식품", 1025: "국내여행",
        1026: "해외여행", 1029: "반려동물용품", 1030: "유아동패션"
    }
    
    category_ids = list(categories.keys())
    category_index = 0
    
    while True:
        try:
            current_category_id = category_ids[category_index % len(category_ids)]
            current_category_name = categories[current_category_id]
            logging.info(f"\n💡 현재 '{current_category_name}' 카테고리로 새로운 상품을 검색합니다...")

            # 5만원 이상 100만원 이하의 상품만 검색
            products = get_products_by_category(category_id=current_category_id, keyword=current_category_name, limit=10, min_price=50000, max_price=1000000)
            
            selected_product = None
            for p in products:
                product_name = p.get('name')
                if product_name and product_name not in posted_products:
                    logging.info(f"✅ 새로운 상품 '{product_name}'을(를) 찾았습니다.")
                    selected_product = p
                    break
                    
            if not selected_product:
                logging.warning(f"'{current_category_name}' 카테고리에서 새로운 상품을 찾지 못했습니다. 다음 카테고리로 넘어갑니다.")
            else:
                posted_products.append(selected_product['name'])
                save_posted_products(posted_products)

                logging.info("2. Gemini AI를 통해 설득력 있는 블로그 글을 생성하는 중...")
                article_content = generate_persuasive_article(selected_product.get('name'))
                
                if article_content:
                    logging.info("3. 마크다운 형식의 블로그 글을 생성하는 중...")
                    blog_post_markdown = generate_full_blog_content(selected_product, article_content)
                    logging.info("✅ 마크다운 생성 완료!")
                    
                    logging.info("4. 깃허브에 글을 게시하는 중...")
                    post_to_github(f"[광고] 인생 아이템! '{selected_product.get('name')}'을(를) 만나보세요.", blog_post_markdown)
                else:
                    logging.error("블로그 글 내용 생성에 실패했습니다. 다음 주기로 넘어갑니다.")

            category_index += 1
            
            # 다음 포스팅까지 2분 대기
            logging.info("⏱️ 다음 포스팅을 위해 2분(120초) 대기 중...")
            time.sleep(120)

        except Exception as e:
            logging.error(f"전체 프로세스 실행 중 오류가 발생했습니다: {e}")
            logging.info("오류가 발생했으나 프로세스는 계속 진행됩니다. 2분 후 다시 시도합니다.")
            time.sleep(120)
