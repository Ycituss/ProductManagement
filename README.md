# 🛒 电商商品管理系统（学习项目）

> <section class="ybc-p">⚠️<span> </span><strong>本项目仅供个人学习与参考，未经作者许可，请勿用于任何商业或公开用途。</strong></section>


## 📌 项目简介
<section class="ybc-p">这是一个用于<strong>电商商品管理</strong>的学习项目，旨在实现对商品信息的增删改查等基础功能，支持商品数据的本地化管理，并结合云存储服务管理商品相关图片与文件。</section><section class="ybc-p">目前主要用于个人技术实践、学习 Python Web 开发、数据库操作、以及云存储（如腾讯云 COS）的集成应用。</section>


## 🏗️ 技术实现 / 功能说明

### 核心功能：

- <section class="ybc-p">商品信息的增删改查（CRUD）</section>
- <section class="ybc-p">商品图片 / 相关文件的上传与管理</section>
- <section class="ybc-p">数据持久化（使用 SQLite）</section>
- <section class="ybc-p">本地文件存储 +<span> </span><strong>腾讯云对象存储（COS）</strong>​ 集成，用于图片等静态资源管理</section>

### 当前实现方式：

- <section class="ybc-p">图片与相关文件采用<span> </span><strong>本地存储 + 腾讯云 COS 混合模式</strong></section>
- <section class="ybc-p">本地存储为主要存储手段</section>
- <section class="ybc-p">腾讯云 COS 用于文件备份</section>


* * *

## ☁️ 腾讯云 COS 说明
<section class="ybc-p">本项目使用<span> </span><span class="hyc-common-markdown__link hyc-common-markdown__link-with-icon"><span class="hyc-common-markdown__link__content">腾讯云对象存储（Cloud Object Storage, COS）</span><svg class="hyc-common-icon hyc-common-markdown__link__content-icon hyc-common-markdown__link-with-icon__icon" width="16" height="16" viewbox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M5.3923 4.5H11.5M11.5 4.5C11.5 7.55385 11.5 10.6077 11.5 10.6077M11.5 4.5L3.5 12.5" stroke-linecap="round" stroke-linejoin="round" stroke="currentColor"></path></svg></span>作为商品图片等静态资源的云存储方案。</section>




## 🚫 使用限制

> <section class="ybc-p">⚠️<span> </span><strong>重要提醒：</strong></section><section class="ybc-p">本项目<span> </span><strong>仅供个人学习、技术研究与参考使用</strong>，<strong>不得用于任何商业用途、产品开发或对外服务</strong>。</section>
> - <section class="ybc-p">未经作者明确许可，<strong>禁止将本项目代码、设计或思路用于任何形式的公开项目、商业产品或服务中</strong>。</section>
> - <section class="ybc-p">本项目未经过完整安全测试、压力测试与合规审查，<strong>不应直接部署于线上生产环境</strong>。</section>
> - <section class="ybc-p">若你基于本项目进行二次开发，建议你遵循相关平台的使用政策（如腾讯云 COS 服务条款等）。</section>
> 

## 🛠️ 如何运行

```
# 1. 克隆项目
git clone https://github.com/Ycituss/ProductManagement.git
cd ProductManagement

# 2. 安装依赖
pip install -r requirements.txt

# 3. 配置环境（COS 配置, key.py中的配置信息需自行填写）
cp key_empty.py key.py

# 4. 运行项目
python app.py
```



## 🤝 联系作者（可选）
 如有疑问或建议，欢迎交流学习（可选填写）：
- <section class="ybc-p">Email: 2799282971@.com</section>
 - <section class="ybc-p">或者直接通过 GitHub Issues 提问</section>


## 📄 License
<section class="ybc-p">本项目采用<span> </span><strong><span class="hyc-common-markdown__link hyc-common-markdown__link-with-icon"><span class="hyc-common-markdown__link__content">MIT License</span><svg class="hyc-common-icon hyc-common-markdown__link__content-icon hyc-common-markdown__link-with-icon__icon" width="16" height="16" viewbox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M5.3923 4.5H11.5M11.5 4.5C11.5 7.55385 11.5 10.6077 11.5 10.6077M11.5 4.5L3.5 12.5" stroke-linecap="round" stroke-linejoin="round" stroke="currentColor"></path></svg></span></strong>，详见项目根目录下的 LICENSE 文件。</section><section class="ybc-p">你可以自由地使用、修改、分发本项目代码，包括用于商业用途，但需保留原版权声明和 LICENSE 文件。</section>

> <section class="ybc-p">📌 提示：虽然代码允许商用，但仍建议合理、负责任地使用，并遵循相关第三方服务（如腾讯云）的使用政策。</section>