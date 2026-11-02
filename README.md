# 🏠 핑포의 작은집 연구소 자동화 (블로그 + 유튜브 쇼츠)

인테리어·살림 꿀팁을 **구글 블로거**에 자동 발행하고, **유튜브 쇼츠**를 자동으로 만들어 올리는 저장소예요. 컴퓨터를 꺼도 GitHub에서 돌아가고, 비용은 들지 않아요.

## 이렇게 돌아가요 (블로그)

1. Claude 예약 작업이 글을 써서 `posts/` 폴더에 JSON으로 올려요.
2. GitHub Actions(`blog-post`)가 바로 블로거에 발행해요.
3. 쿠팡 상품이 있으면 글 맨 위에 대가성 문구 상자, 글 끝에 상품 상자를 붙여요.
4. 글 끝에 유튜브·스레드 채널 링크를 붙여요.
5. 발행 기록은 `data/posted.json`에 남아 같은 글을 두 번 올리지 않아요.

## GitHub 비밀값 (Settings → Secrets and variables → Actions)

**Secrets 탭** (남에게 안 보임)

| 이름 | 값 |
|---|---|
| GOOGLE_CLIENT_ID | 구글 클라우드 OAuth 클라이언트 ID |
| GOOGLE_CLIENT_SECRET | 구글 클라우드 OAuth 보안 비밀번호 |
| GOOGLE_REFRESH_TOKEN | OAuth Playground에서 받은 Refresh token |
| BLOGGER_BLOG_ID | 블로거 주소창의 `blogID=` 뒤 숫자 |
| TELEGRAM_BOT_TOKEN | (선택) 텔레그램 알림 봇 토큰 |
| TELEGRAM_CHAT_ID | (선택) 텔레그램 채팅 ID |

**Variables 탭** (공개돼도 괜찮은 값)

| 이름 | 값 |
|---|---|
| YOUTUBE_CHANNEL_URL | 내 유튜브 채널 주소 (예: `https://www.youtube.com/@핸들`) |
| THREADS_URL | 내 스레드 주소 (예: `https://www.threads.com/@핸들`) |
| CONTACT_EMAIL | 문의 페이지에 보일 이메일 |

## 쿠팡 상품 넣기

`data/coupang_links.txt`에 `단축링크 | 상품명 | 분류` 형식으로 한 줄씩 추가해요.
쿠팡 파트너스 **내 정보 → 웹사이트/채널**에 내 블로그 주소를 꼭 등록해 주세요.

## 블로그 페이지 (소개·개인정보처리방침·문의)

`pages/` 폴더 내용을 Actions → `blog-pages` → Run workflow 로 한 번 실행하면 블로그에 페이지가 생겨요.

## 애드센스 신청 시기

글이 20~30편 쌓이고, 소개·개인정보처리방침·문의 페이지가 있는 상태에서 신청하는 게 좋아요.

---

# 📰 두 번째 채널: 핑포의 오늘뉴스 (`news/` 폴더)

살림 채널과 **같은 코드**를 쓰고, 워크플로에서 `CHANNEL: news` 로 폴더·문구만 바꿔요. 살림 채널 파일은 건드리지 않아요.

| 무엇 | 살림 (그대로) | 뉴스 |
|---|---|---|
| 블로그 | pinkpoket.blogspot.com | pinkpoket-news.blogspot.com (blogID 5147989058215304792) |
| 유튜브 | 핑포의 작은집 연구소 | @핑포의오늘뉴스 (UC3QKRPjjKXiPWVKxfi5vSTQ) |
| 글 폴더 | `posts/` | `news/posts/` |
| 쇼츠 대본 | `shorts/queue/` | `news/shorts/queue/` |
| 페이지 | `pages/` | `news/pages/` |
| 기록 | `data/` | `news/data/` |
| 워크플로 | blog-post · shorts-make · blog-pages | blog-news-post · shorts-news-make · blog-news-pages |
| 규칙 | WRITING_GUIDE.md · SHORTS_GUIDE.md | news/WRITING_GUIDE.md · news/SHORTS_GUIDE.md |

뉴스 채널에 새로 필요한 비밀값은 하나예요: **`NEWS_YOUTUBE_REFRESH_TOKEN`** (오늘뉴스 채널을 골라 받은 유튜브 토큰).
구글 클라이언트·블로그 토큰·Cloudflare·텔레그램·쿠팡 키는 살림 채널 것을 같이 써요.
업로드 전에 채널 ID를 확인하니, 토큰을 잘못 넣어도 살림 채널에 뉴스가 올라가지 않아요.
