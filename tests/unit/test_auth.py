from unittest.mock import MagicMock, patch

import src.auth as auth


class TestGetYoutubeCredentials:
    def test_retorna_none_sem_token_json(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        assert auth.get_youtube_credentials() is None

    def test_retorna_none_se_token_corrompido(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "token.json").write_text("não é json válido", encoding="utf-8")
        assert auth.get_youtube_credentials() is None

    def test_retorna_creds_validas_sem_refresh(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "token.json").write_text("{}", encoding="utf-8")

        fake_creds = MagicMock(valid=True)
        with patch.object(auth.Credentials, "from_authorized_user_file", return_value=fake_creds):
            result = auth.get_youtube_credentials()

        assert result is fake_creds

    def test_renova_token_expirado_com_refresh_token(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "token.json").write_text("{}", encoding="utf-8")

        fake_creds = MagicMock(valid=False, expired=True, refresh_token="abc")
        fake_creds.to_json.return_value = '{"renovado": true}'

        with patch.object(auth.Credentials, "from_authorized_user_file", return_value=fake_creds):
            with patch.object(auth, "Request"):
                result = auth.get_youtube_credentials()

        fake_creds.refresh.assert_called_once()
        assert result is fake_creds
        assert (tmp_path / "token.json").read_text(encoding="utf-8") == '{"renovado": true}'

    def test_retorna_none_sem_refresh_token(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "token.json").write_text("{}", encoding="utf-8")

        fake_creds = MagicMock(valid=False, expired=True, refresh_token=None)

        with patch.object(auth.Credentials, "from_authorized_user_file", return_value=fake_creds):
            result = auth.get_youtube_credentials()

        assert result is None

    def test_nunca_chama_fluxo_interativo(self):
        """
        Regressão: get_youtube_credentials() não deve depender de
        InstalledAppFlow/run_local_server — isso quebra em servidor
        headless (causa raiz do "Missing code verifier").
        """
        assert not hasattr(auth, "InstalledAppFlow")
