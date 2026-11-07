# REPLIKA · статический лендинг

Одна HTML-страница и локальный CSS. Сборка, JavaScript, внешние шрифты,
библиотеки, аналитика и трекеры не нужны. Светлая и тёмная темы выбираются
системной настройкой `prefers-color-scheme`.

## Локальный просмотр

Из корня репозитория:

```sh
python3 -m http.server 8000 --directory site
```

Откройте <http://localhost:8000>. Можно также открыть `site/index.html` напрямую.

## Что заменить перед финальной публикацией

- В таблице результатов заменить три буквальных `{{TBD}}` реальными WER, DER,
  RTF и добавить условия измерения. Сейчас таблица не заявляет результатов.
- Вместо трёх `.screenshot-placeholder` разместить реальные скриншоты с
  содержательными `alt`. Хранить изображения внутри `site/`, использовать
  относительные пути и указать размеры, чтобы избежать скачков вёрстки.
- Заполнить участников команды и их роли в разделе «Команда».

Изображение стенограммы в герое — схема, выполненная HTML/CSS, а не скриншот
приложения. Кнопка «Скачать APK» ведёт на
[Releases](https://github.com/XterrK/ReplikaAndroid/releases).

## GitHub Pages для `site/`

В режиме **Deploy from a branch** GitHub предлагает только `/ (root)` или
`/docs`. Выбрать `/site` там нельзя. Для публикации содержимого `site/` в корне
сайта используйте GitHub Actions, без сборки.

В этом PR workflow **не установлен**: все изменения ограничены `site/`.
После отдельного решения о публикации:

1. Откройте репозиторий → **Settings → Pages → Build and deployment → Source →
   GitHub Actions**. Для приватного репозитория доступность Pages зависит от
   тарифа; менять видимость репозитория не требуется.
2. Добавьте отдельным изменением файл `.github/workflows/pages.yml` из примера
   ниже. Он публикует только `site/`, а не содержимое всего репозитория.
3. Для окружения **Settings → Environments → github-pages** разрешите
   развёртывания из `hack/final`, если включены ограничения веток.
4. После попадания лендинга и workflow в `hack/final` дождитесь успешного
   запуска **Deploy REPLIKA landing** на вкладке **Actions**. Ручной запуск
   `workflow_dispatch` доступен, когда файл workflow есть в default branch;
   выбирайте при запуске `hack/final`. Для другой ветки публикации замените
   обе проверки `hack/final` в примере и настройку окружения.
5. Откройте URL из шага deployment или **Settings → Pages**. Без собственного
   домена обычный адрес: `https://xterrk.github.io/ReplikaAndroid/`.

```yaml
name: Deploy REPLIKA landing

on:
  push:
    branches: ["hack/final"]
    paths:
      - "site/**"
      - ".github/workflows/pages.yml"
  workflow_dispatch:

permissions:
  contents: read
  pages: write
  id-token: write

concurrency:
  group: pages
  cancel-in-progress: false

jobs:
  deploy:
    if: github.ref == 'refs/heads/hack/final'
    runs-on: ubuntu-latest
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}
    steps:
      - name: Checkout
        uses: actions/checkout@v6
        with:
          sparse-checkout: site
      - name: Configure Pages
        uses: actions/configure-pages@v5
      - name: Upload static site
        uses: actions/upload-pages-artifact@v4
        with:
          path: site
      - name: Deploy
        id: deployment
        uses: actions/deploy-pages@v4
```

Сайт имеет относительную ссылку на CSS и работает под префиксом
`/ReplikaAndroid/`. Файл `.nojekyll` позволяет использовать те же файлы при
альтернативной публикации без Jekyll. Содержимое `site/` предназначено для
публичного доступа; права на исходный приватный репозиторий и Releases остаются
прежними.

Официальные инструкции:
[источники публикации](https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site),
[workflow для Pages](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages).
