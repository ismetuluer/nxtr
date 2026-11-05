"""`python -m nxceviri` uygulamayı başlatır; `python -m nxceviri <komut>` komut satırı araçlarını çalıştırır."""

import sys


def _run(args: list[str]) -> int:
    from nxceviri.arac import komut_mu  # noqa: PLC0415 - arayüz yüklenmeden karar verilir

    if komut_mu(args):
        from nxceviri.arac import main as tool_main  # noqa: PLC0415 - komut satırında arayüz yüklenmesin

        return tool_main(args)
    # Bilinmeyen bağımsız değişkenler (sürüklenen oyun dosyası, Qt bayrağı…) arayüzü kapatmaz; arayüz yalnızca
    # `.nxproj` yollarını kullanır, gerisini yok sayar.
    from nxceviri.gui.app import main  # noqa: PLC0415 - arayüz yalnızca gerekince yüklenir

    return main()


if __name__ == "__main__":
    sys.exit(_run(sys.argv[1:]))
