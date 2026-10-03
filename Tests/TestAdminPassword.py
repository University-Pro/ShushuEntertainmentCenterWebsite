"""首次登录改密与旧数据库兼容性回归测试，使用独立临时数据库。"""

import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pyotp
from werkzeug.security import generate_password_hash

import AppConfig
from Core import Analytics, Database, Repository
from RunServer import CreateApplication


class AdminPasswordTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.DataFolder = Path(temporary.name)
        self.DatabaseFile = self.DataFolder / "MainPage.db"
        for target, name, value in (
            (Database, "DATA_FOLDER", self.DataFolder),
            (Database, "DATABASE_FILE", self.DatabaseFile),
            (AppConfig, "DATA_FOLDER", self.DataFolder),
            (AppConfig, "SECRET_KEY_FILE", self.DataFolder / "SecretKey.txt"),
            (Analytics, "_SecretKeyCache", None),
        ):
            replacement = patch.object(target, name, value)
            replacement.start()
            self.addCleanup(replacement.stop)
        environment = patch.dict("os.environ", {"SHUSHU_SECRET_KEY": "test-only-session-key"})
        environment.start()
        self.addCleanup(environment.stop)
        self.Application = CreateApplication()
        self.Application.config.update(TESTING=True, SESSION_COOKIE_SECURE=False)
        self.Client = self.Application.test_client()

    def Login(self, client=None, password="admin"):
        return (client or self.Client).post("/Admin/Api/Login", json={
            "UserName": "admin", "Password": password,
        })

    def ChangePassword(self, client=None, old="admin", new="new-password-123"):
        return (client or self.Client).post("/Admin/Api/ChangePassword", json={
            "OldPassword": old, "NewPassword": new,
        })

    def test_DefaultLoginRequiresPasswordChange(self):
        response = self.Login()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json["Data"]["NeedPasswordChange"])
        self.assertTrue(Repository.GetAdmin("admin")["MustChangePassword"])
        page = self.Client.get("/Admin/")
        self.assertEqual(page.location, "/Admin/ChangePassword")
        page = self.Client.get("/Admin/ChangePassword")
        self.assertEqual(page.status_code, 200)
        self.assertIn(b'InitialPasswordForm', page.data)

    def test_AllProtectedRoutesAreBlockedBeforeChange(self):
        self.Login()
        for rule in self.Application.url_map.iter_rules():
            if not rule.rule.startswith("/Admin/") or "<" in rule.rule:
                continue
            if rule.rule in (
                "/Admin/Login", "/Admin/ChangePassword", "/Admin/Api/Login",
                "/Admin/Api/VerifyTotp", "/Admin/Api/ChangePassword", "/Admin/Api/Logout",
            ):
                continue
            with self.subTest(route=rule.rule):
                method = "POST" if "POST" in rule.methods else "GET"
                response = self.Client.open(rule.rule, method=method, json={})
                if rule.rule.startswith("/Admin/Api/"):
                    self.assertEqual(response.status_code, 403)
                    self.assertTrue(response.json["Data"]["NeedPasswordChange"])
                else:
                    self.assertEqual(response.status_code, 302)
                    self.assertEqual(response.location, "/Admin/ChangePassword")

    def test_InvalidChangesDoNotUnlockAccount(self):
        self.Login()
        for old, new in (("wrong", "new-password-123"), ("admin", "admin"), ("admin", "short")):
            self.assertEqual(self.ChangePassword(old=old, new=new).status_code, 400)
            self.assertTrue(Repository.GetAdmin("admin")["MustChangePassword"])
        self.assertEqual(self.Client.get("/Admin/Api/Overview").status_code, 403)

    def test_SuccessfulChangeUnlocksAndPersists(self):
        self.Login()
        self.assertEqual(self.ChangePassword().status_code, 200)
        self.assertEqual(self.Client.get("/Admin/Api/Overview").status_code, 200)
        self.assertEqual(self.Client.get("/Admin/").status_code, 200)
        self.assertFalse(Repository.GetAdmin("admin")["MustChangePassword"])
        self.assertIsNone(Repository.VerifyAdmin("admin", "admin"))
        CreateApplication()
        self.assertEqual(Repository.VerifyAdmin("admin", "new-password-123"), "admin")
        self.Client.post("/Admin/Api/Logout")
        response = self.Login(password="new-password-123")
        self.assertFalse(response.json["Data"]["NeedPasswordChange"])

    def test_ChangeRevokesOtherBootstrapSessions(self):
        other = self.Application.test_client()
        self.Login()
        self.Login(other)
        self.ChangePassword()
        self.assertEqual(other.get("/Admin/Api/Overview").status_code, 401)
        self.assertEqual(self.ChangePassword(other).status_code, 401)
        self.assertEqual(self.Client.get("/Admin/Api/Overview").status_code, 200)

    def test_SessionFlagCannotBypassDatabaseRequirement(self):
        self.Login()
        with self.Client.session_transaction() as session:
            session["MustChangePassword"] = False
        self.assertEqual(self.Client.get("/Admin/Api/Overview").status_code, 403)

    def test_UnauthenticatedChangeIsRejected(self):
        self.assertEqual(self.ChangePassword().status_code, 401)
        self.assertEqual(self.Client.get("/Admin/ChangePassword").location, "/Admin/Login")

    def MigrateLegacyAccount(self, password):
        with sqlite3.connect(self.DatabaseFile) as connection:
            connection.execute("DROP TABLE AdminAccount")
            connection.execute("""CREATE TABLE AdminAccount (
                Id INTEGER PRIMARY KEY, UserName TEXT UNIQUE, PasswordHash TEXT,
                UpdatedAt TEXT DEFAULT (datetime('now', 'localtime'))
            )""")
            connection.execute(
                "INSERT INTO AdminAccount (UserName, PasswordHash) VALUES (?, ?)",
                ("admin", generate_password_hash(password)),
            )
        CreateApplication()

    def test_LegacyCustomPasswordIsPreserved(self):
        self.MigrateLegacyAccount("existing-password-123")
        response = self.Login(password="existing-password-123")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json["Data"]["NeedPasswordChange"])
        self.assertEqual(self.Client.get("/Admin/Api/Overview").status_code, 200)

    def test_LegacyDefaultPasswordRequiresChange(self):
        self.MigrateLegacyAccount("admin")
        self.assertTrue(self.Login().json["Data"]["NeedPasswordChange"])
        self.assertEqual(self.Client.get("/Admin/Api/Overview").status_code, 403)

    def test_TotpCannotBypassChangeAndPendingSessionIsRevoked(self):
        secret = pyotp.random_base32()
        Repository.SaveTotpSecret("admin", secret)
        Repository.EnableTotp("admin", "[]")
        other = self.Application.test_client()
        self.assertTrue(self.Login().json["Data"]["NeedTotp"])
        self.Login(other)
        self.assertEqual(self.Client.get("/Admin/Api/Overview").status_code, 401)
        # The rejected request clears the pending session; log in again.
        self.Login()
        response = self.Client.post("/Admin/Api/VerifyTotp", json={"Code": pyotp.TOTP(secret).now()})
        self.assertTrue(response.json["Data"]["NeedPasswordChange"])
        self.assertEqual(self.Client.get("/Admin/Api/Overview").status_code, 403)
        self.ChangePassword()
        response = other.post("/Admin/Api/VerifyTotp", json={"Code": pyotp.TOTP(secret).now()})
        self.assertEqual(response.status_code, 401)


if __name__ == "__main__":
    unittest.main()
