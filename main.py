import requests
import re
import time
import os
import ddddocr
import base64
from bs4 import BeautifulSoup
from PIL import Image, ImageDraw
from io import BytesIO
import img2pdf


class GBStandardDownloader:
    def __init__(self, document_url=None):
        self.base_url = "http://c.gb688.cn/bzgk/gb/"
        self.document_url = (
            document_url
            or "http://c.gb688.cn/bzgk/gb/showGb?type=online&hcno=9E5467EA1922E8342AF5F180319F34A0"
        )
        self.session = requests.Session()
        self.jsessionid = None
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "Accept": "*/*",
            "Host": "c.gb688.cn",
            "Referer": self.document_url,  # 使用文档URL作为Referer
            "Accept-Encoding": "gzip, deflate",
            "Cache-Control": "max-age=0",
            "Proxy-Connection": "keep-alive",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Upgrade-insecure-Requests": "1",
        }
        self.ocr = ddddocr.DdddOcr()
        self.output_dir = "gb_standard_images"
        os.makedirs(self.output_dir, exist_ok=True)

    def get_jsessionid(self):
        """第一步：获取JSESSIONID"""
        url = "http://c.gb688.cn/bzgk/gb/showGb?type=download&hcno=F60B16F6F204597DDAFD8CCCFC931E11"
        response = self.session.get(url, headers=self.headers)

        # 从Set-Cookie中提取JSESSIONID
        cookies = response.headers.get("Set-Cookie", "")
        jsessionid_match = re.search(r"JSESSIONID=([^;]+)", cookies)

        if jsessionid_match:
            self.jsessionid = jsessionid_match.group(1)
            print(f"获取到JSESSIONID: {self.jsessionid}")
            # 更新headers中的Cookie
            self.headers["Cookie"] = f"JSESSIONID={self.jsessionid};"
            return True
        else:
            print("未能获取JSESSIONID")
            return False

    def get_verify_code(self):
        """第二步：获取验证码并识别"""
        url = f"{self.base_url}gc"
        response = self.session.get(url, headers=self.headers)

        if response.status_code == 200:
            # 使用ddddocr库识别验证码
            verify_code = self.ocr.classification(response.content)
            print(f"识别的验证码: {verify_code}")
            return verify_code
        else:
            print(f"获取验证码失败，状态码: {response.status_code}")
            return None

    def verify_code(self, code):
        """第三步：提交验证码"""
        url = f"{self.base_url}verifyCode"
        form_data = {"verifyCode": code}

        response = self.session.post(url, data=form_data, headers=self.headers)

        if response.status_code == 200:
            if response.text == "success":
                print("验证码验证成功")
                return True
            else:
                print(f"验证码验证失败: {result}")
                return False
        else:
            print(f"提交验证码请求失败，状态码: {response.status_code}")
            return False

    def get_standard_html(self):
        """第四步：获取标准文档的HTML内容"""
        response = self.session.get(self.document_url, headers=self.headers)

        if response.status_code == 200:
            print("成功获取标准文档HTML")
            return response.text
        else:
            print(f"获取标准文档HTML失败，状态码: {response.status_code}")
            return None

    def extract_image_info(self, html_content):
        """第五步：从HTML中提取图片信息和页面结构，处理重复bg的情况"""
        soup = BeautifulSoup(html_content, "html.parser")

        # 提取CSS样式
        style_tags = soup.find_all("style")
        css_content = "\n".join([style.string for style in style_tags if style.string])

        # 提取页面信息和对应的bg值
        page_images = []
        unique_bg_values = set()  # 用于记录已经见过的bg值

        # 查找所有页面元素
        page_divs = soup.find_all("div", class_="page")

        for page_div in page_divs:
            bg_value = page_div.get("bg")
            if bg_value:
                page_images.append(bg_value)
                unique_bg_values.add(bg_value)

        print(
            f"找到 {len(page_images)} 个页面，其中包含 {len(unique_bg_values)} 个唯一的bg值"
        )
        return page_images, css_content, unique_bg_values

    def download_images(self, page_images, unique_bg_values):
        """第六步：下载所有页面图片，处理重定向获取真实图片，避免重复下载"""
        # 创建一个字典来存储bg值到图片路径的映射
        bg_to_image_path = {}

        # 首先下载所有唯一的图片
        for i, bg_value in enumerate(unique_bg_values):
            url = f"http://c.gb688.cn/bzgk/gb/viewGbImg?fileName={bg_value}"

            # 设置不自动处理重定向，以便我们可以获取重定向URL
            response = self.session.get(
                url, headers=self.headers, allow_redirects=False
            )

            if response.status_code == 302:  # 重定向状态码
                # 获取重定向的真实图片URL
                real_img_url = response.headers.get("Location")
                if real_img_url:
                    # 确保URL是绝对路径
                    if not real_img_url.startswith("http"):
                        if real_img_url.startswith("/"):
                            real_img_url = f"http://c.gb688.cn{real_img_url}"
                        else:
                            real_img_url = f"http://c.gb688.cn/{real_img_url}"

                    print(f"获取到真实图片URL: {real_img_url}")

                    self.headers["Cache-Alive"] = f"chunked"
                    self.headers["Proxy-Connection"] = f"keep-alive"
                    self.headers["Accept-Encoding"] = f"gzip, deflate"
                    # 下载真实图片，确保带上cookie
                    img_response = self.session.get(real_img_url, headers=self.headers)

                    if img_response.status_code == 200:
                        # 保存图片
                        output_path = os.path.join(
                            self.output_dir, f"unique_bg_{i+1}.png"
                        )
                        with open(output_path, "wb") as f:
                            f.write(img_response.content)

                        print(f"成功下载bg图片: {bg_value}")
                        bg_to_image_path[bg_value] = output_path
                    else:
                        print(f"下载真实图片失败，状态码: {img_response.status_code}")
                else:
                    print(f"未找到重定向URL，无法下载bg图片: {bg_value}")
            else:
                print(f"获取图片重定向失败，状态码: {response.status_code}")

        # 然后按照页面顺序返回图片路径列表
        image_files = []
        for bg_value in page_images:
            if bg_value in bg_to_image_path:
                image_files.append(bg_to_image_path[bg_value])
            else:
                # 如果某个bg值对应的图片下载失败，用占位图或者None
                print(f"警告：bg值 {bg_value} 的图片未能成功下载")
                image_files.append(None)

        return image_files

    def process_images_with_sprite(self, html_content, image_files):
        """根据HTML中的精灵图定位信息重构完整页面"""
        from PIL import Image
        import re
        from bs4 import BeautifulSoup

        processed_pages = []
        soup = BeautifulSoup(html_content, "html.parser")

        # 查找所有页面元素
        page_divs = soup.find_all("div", class_="page")

        for page_index, page_div in enumerate(page_divs):
            # 获取页面尺寸
            page_style = page_div.get("style", "")
            width_match = re.search(r"width:(\d+)px", page_style)
            height_match = re.search(r"height:(\d+)px", page_style)

            if width_match and height_match:
                page_width = int(width_match.group(1))
                page_height = int(height_match.group(1))
            else:
                # 默认尺寸
                page_width = 2315
                page_height = 3274

            # 创建一个空白页面(白色背景)
            page_image = Image.new("RGB", (page_width, page_height), (255, 255, 255))

            # 获取对应的原始图片
            bg_value = page_div.get("bg")
            if not bg_value or page_index >= len(image_files):
                print(f"跳过第 {page_index+1} 页，缺少背景图片或图片文件")
                continue

            # 打开原始图片
            try:
                source_image = Image.open(image_files[page_index])
            except Exception as e:
                print(f"无法打开第 {page_index+1} 页图片: {e}")
                continue

            # 处理每个span元素(精灵图片的一个部分)
            spans = page_div.find_all("span")
            for span in spans:
                # 获取class和background-position
                span_class = span.get("class", [""])[0]  # 例如: "pdfImg-6-1"
                bg_position = span.get("style", "")

                # 从background-position中提取x和y偏移
                position_match = re.search(
                    r"background-position:\s*(-?\d+)px\s+(-?\d+)px", bg_position
                )
                if not position_match:
                    continue

                # 负偏移值表示精灵图的起始位置
                sprite_x = -int(position_match.group(1))
                sprite_y = -int(position_match.group(2))

                # 从class中提取位置信息 (例如: "pdfImg-6-1" -> x=6, y=1)
                class_match = re.search(r"pdfImg-(\d+)-(\d+)", span_class)
                if not class_match:
                    continue

                grid_x = int(class_match.group(1))
                grid_y = int(class_match.group(2))

                # 计算在页面上的位置 (根据CSS样式表中的规则)
                # 这些值需要根据实际CSS规则调整
                dest_x = int(grid_x * (page_width / 10))  # left: X0%
                dest_y = int(grid_y * (page_height / 10))  # top: Y0%

                # 精灵图片的大小 (需要根据实际情况调整)
                # 假设每个sprite是页面宽度和高度的10%
                sprite_width = int(page_width / 10)
                sprite_height = int(page_height / 10)

                # 从原始图片裁剪出精灵图片部分
                try:
                    sprite = source_image.crop(
                        (
                            sprite_x,
                            sprite_y,
                            sprite_x + sprite_width,
                            sprite_y + sprite_height,
                        )
                    )

                    # 将精灵图片粘贴到页面上的正确位置
                    page_image.paste(sprite, (dest_x, dest_y))
                except Exception as e:
                    print(
                        f"处理精灵图片失败: {e}, 位置: {sprite_x},{sprite_y} -> {dest_x},{dest_y}"
                    )

            # 保存处理好的页面
            output_path = os.path.join(
                self.output_dir, f"reconstructed_page_{page_index+1}.png"
            )
            page_image.save(output_path)
            processed_pages.append(output_path)
            print(f"已重构第 {page_index+1} 页")

        return processed_pages

    def extract_standard_number(self, html_content):
        """从HTML标题中提取标准号，如'GB/T 22239-2019'"""
        soup = BeautifulSoup(html_content, "html.parser")
        title_tag = soup.find("title")

        if title_tag and title_tag.string:
            # 尝试从标题中提取标准号
            title_text = title_tag.string
            # 匹配常见标准号格式，如"GB/T 22239-2019"
            standard_number_match = re.search(
                r"([A-Z]+/[A-Z]+\s+\d+-\d+|[A-Z]+\s+\d+-\d+)", title_text
            )

            if standard_number_match:
                return standard_number_match.group(1)

        # 如果提取失败，返回默认文件名
        return "standard_document"

    def generate_pdf(self, image_files, standard_number):
        """生成PDF文件，使用标准号作为文件名"""
        # 替换标准号中的特殊字符，使其适合作为文件名
        safe_standard_number = standard_number.replace("/", "_").replace(" ", "_")
        output_pdf = f"{safe_standard_number}.pdf"

        # 过滤掉None值（可能是下载失败的图片）
        valid_image_files = [
            img_path for img_path in image_files if img_path is not None
        ]

        if not valid_image_files:
            print("没有有效的图片可以生成PDF")
            return None

        with open(output_pdf, "wb") as f:
            f.write(
                img2pdf.convert(
                    [Image.open(img_path).filename for img_path in valid_image_files]
                )
            )

        print(f"已生成PDF文件: {output_pdf}")
        return output_pdf

    def run(self):
        """执行完整流程"""
        # 步骤1: 获取JSESSIONID
        if not self.get_jsessionid():
            return False

        # 步骤2和3: 获取并验证验证码
        max_attempts = 3
        for attempt in range(max_attempts):
            verify_code = self.get_verify_code()
            if verify_code and self.verify_code(verify_code):
                break
            print(f"验证码验证失败，尝试次数: {attempt+1}/{max_attempts}")
            if attempt == max_attempts - 1:
                print("验证码验证失败次数过多，退出")
                return False

        # 步骤4和5: 获取标准文档HTML并提取图片信息
        html_content = self.get_standard_html()
        if not html_content:
            return False

        # 提取标准号
        standard_number = self.extract_standard_number(html_content)
        print(f"提取到标准号: {standard_number}")

        page_images, css_content, unique_bg_values = self.extract_image_info(
            html_content
        )

        # 步骤6: 下载所有页面图片
        image_files = self.download_images(page_images, unique_bg_values)

        # 步骤7: 处理图片并生成PDF
        processed_images = self.process_images_with_sprite(html_content, image_files)
        pdf_path = self.generate_pdf(processed_images, standard_number)

        return pdf_path


def main():
    # 提示用户输入URL
    print("GB标准文档下载工具")
    print("-------------------")
    print("请输入要下载的GB标准文档URL，格式如:")
    print(
        "http://c.gb688.cn/bzgk/gb/showGb?type=online&hcno=9E5467EA1922E8342AF5F180319F34A0"
    )

    url = input("请输入URL: ").strip()

    # 验证URL格式
    if not url.startswith("http://c.gb688.cn/bzgk/gb/showGb"):
        print("URL格式不正确，请提供正确的GB标准文档URL")
        return

    # 创建下载器实例并设置文档URL
    downloader = GBStandardDownloader(document_url=url)
    result = downloader.run()

    if result:
        print(f"成功下载并生成PDF: {result}")
        print(f"文件保存在: {os.path.abspath(result)}")
    else:
        print("下载失败")


if __name__ == "__main__":
    main()
