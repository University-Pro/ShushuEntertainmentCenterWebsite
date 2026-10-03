"""公开访问的路由：首页、只读数据接口与爬虫协议。"""

from flask import Blueprint, jsonify, render_template, send_from_directory

from AppConfig import STATIC_FOLDER
from Core.Repository import BuildSiteContent

PublicBlueprint = Blueprint("PublicApi", __name__)


@PublicBlueprint.route("/", methods=["GET"])
def IndexPage():
    """首页。"""
    return render_template("IndexPage.html", Content=BuildSiteContent())


@PublicBlueprint.route("/Api/SiteContent", methods=["GET"])
def SiteContent():
    """首页数据的 JSON 版本，供前端刷新或二次开发使用。"""
    return jsonify({"Success": True, "Data": BuildSiteContent()})


@PublicBlueprint.route("/Health", methods=["GET"])
def HealthCheck():
    """健康检查，便于反向代理探活。"""
    return jsonify({"Success": True, "Message": "ShuShu MainPage is running"})


@PublicBlueprint.route("/robots.txt", methods=["GET"])
def RobotsTxt():
    """爬虫协议。

    必须挂在站点根路径：爬虫只读根目录这一份，不会去 /Static/ 下找。
    文件本体放在 Web/Static/ 里，改文案不必动代码。
    """
    return send_from_directory(STATIC_FOLDER, "robots.txt", mimetype="text/plain")