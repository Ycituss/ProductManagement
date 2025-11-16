from qcloud_cos import CosConfig
from qcloud_cos import CosS3Client
import sys
import logging
import key

# 设置日志（可选，调试用）
logging.basicConfig(level=logging.INFO, stream=sys.stdout)

def upload_to_cos(file_path, cos_path):
    # ============================
    # 第一步：填入你的腾讯云密钥和存储桶信息
    # ============================

    secret_id = key.secret_id         # 替换为你的 SecretId
    secret_key = key.secret_key     # 替换为你的 SecretKey
    region = key.region            # 替换为你的存储桶地域，如 ap-shanghai, ap-beijing
    bucket = key.bucket     # 例如：examplebucket-1250000000

    # 本地文件路径（你要上传的文件）
    local_file_path = file_path     # 例如当前目录下的 test.jpg

    # 文件在 COS 上的路径（即 object key，可以是文件夹结构，如 images/test.jpg）
    cos_key = cos_path        # 上传到 COS 后的路径 / 文件名

    # ============================
    # 第二步：初始化 COS 客户端
    # ============================

    config = CosConfig(Region=region, SecretId=secret_id, SecretKey=secret_key)
    client = CosS3Client(config)

    # ============================
    # 第三步：上传文件到 COS，并设置 ACL 为 public-read（公有读）
    # ============================

    try:
        response = client.upload_file(
            Bucket=bucket,
            LocalFilePath=local_file_path,
            Key=cos_key,               # COS 上的文件路径，如 images/test.jpg
            ACL='public-read',         # 关键：设置文件为“公有读”，这样才有可公开访问的链接
            ContentDisposition='inline'
        )
        print("✅ 文件上传成功！")

        # ============================
        # 第四步：拼接可访问的外链 URL
        # ============================

        # COS 文件外链的基本格式：
        # https://<Bucket>.cos.<Region>.myqcloud.com/<Key>
        cos_domain = f"https://{bucket}.cos.{region}.myqcloud.com"
        file_url = f"{cos_domain}/{cos_key}"

        print(f"🔗 文件外链（可直接访问）: {file_url}")
        return file_url

    except Exception as e:
        print(f"❌ 文件上传失败: {e}")
        return ''

# upload_to_cos('./static/uploads/test4/00a89d9e-3bb2-4914-849b-f0d65a470186.png', 'image/test/test1.png')