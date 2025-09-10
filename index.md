layout: default title: '나만의 쿠팡 파트너스 블로그'
최신 상품 리뷰
{% for post in site.posts %}

<div class="post-item">
<h3><a href="{{ site.baseurl }}{{ post.url }}">{{ post.title }}</a></h3>
<p>{{ post.excerpt | strip_html | strip_newlines | truncate: 200 }}</p>
<a href="{{ site.baseurl }}{{ post.url }}">더 읽어보기</a>
</div>
{% endfor %}
