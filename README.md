# rkn-checker-tui

Дружелюбная TUI-обертка над [rkn-block-checker](https://github.com/MayersScott/rkn-block-checker): меню вместо флагов, пресеты вместо параметров, понятные описания вердиктов на русском, история снапшотов с диффом.

Под капотом — тот же движок, что и в оригинале: послойная диагностика блокировок (DNS → TCP → TLS → HTTP). TUI меняет только то, как с этим работает человек.

## Статус

Альфа. Не для прода.

## Установка

```bash
pipx install rkn-checker-tui
```

Или из репо:

```bash
git clone https://github.com/howdeploy/rkn-checker-tui
cd rkn-checker-tui
pipx install --editable .
```

## Запуск

```bash
rkn-tui
```

## Кредит

Probe-движок — [rkn-block-checker](https://github.com/MayersScott/rkn-block-checker) (MIT) автора Dmitry Vinogradov. TUI и обертка — отдельный проект, не аффилирован с автором оригинала.

## Лицензия

MIT.
