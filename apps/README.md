# apps/

(선택) 커스텀 Omniverse Kit `.kit` 앱 정의를 두는 곳.

지금은 비어 있음. kit-app-template을 그대로 런타임 호스트로 쓰면 여기 없어도 됨.

자급형 앱을 만들고 싶으면:
1. kit-app-template에서 `repo template new` 로 usd_viewer/usd_composer 베이스 앱 스캐폴딩.
2. 생성된 `.kit`의 `[settings.app.exts.folders]` `'++'` 에 `"C:/dev/vps_omniverse/exts"` 추가.
3. `[dependencies]` 에 `"vps.live.viz" = {}` 추가.
4. 그 `.kit`을 여기 복사해 버전관리.
