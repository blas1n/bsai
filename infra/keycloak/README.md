# Keycloak Configuration

## Quick Start

Keycloak이 Docker Compose로 자동 실행됩니다:

```bash
# DevContainer 재시작 후 접속
http://localhost:8080

# Admin Console 로그인
Username: admin
Password: admin
```

## 테스트 계정

| Email | Password | Role |
|-------|----------|------|
| test@example.com | testpassword | user |
| admin@example.com | adminpassword | admin |

## 소셜 로그인 설정

### Google

1. [Google Cloud Console](https://console.cloud.google.com/) 접속
2. OAuth 2.0 Client ID 생성
   - Authorized redirect URI: `http://localhost:8080/realms/bsai/broker/google/endpoint`
3. Keycloak Admin Console → Identity Providers → Add provider → Google
4. Client ID와 Client Secret 입력

### GitHub

1. [GitHub Developer Settings](https://github.com/settings/developers) 접속
2. New OAuth App 생성
   - Authorization callback URL: `http://localhost:8080/realms/bsai/broker/github/endpoint`
3. Keycloak → Identity Providers → Add provider → GitHub
4. Client ID와 Client Secret 입력

### Kakao

1. [Kakao Developers](https://developers.kakao.com/) 접속
2. 애플리케이션 생성
3. 카카오 로그인 활성화
   - Redirect URI: `http://localhost:8080/realms/bsai/broker/kakao/endpoint`
4. Keycloak → Identity Providers → Add provider → OpenID Connect
   - Alias: `kakao`
   - Authorization URL: `https://kauth.kakao.com/oauth/authorize`
   - Token URL: `https://kauth.kakao.com/oauth/token`
   - Client ID: REST API 키
   - Client Secret: Client Secret 코드

### Naver

1. [Naver Developers](https://developers.naver.com/) 접속
2. 애플리케이션 등록
   - 서비스 URL: `http://localhost:3000`
   - Callback URL: `http://localhost:8080/realms/bsai/broker/naver/endpoint`
3. Keycloak → Identity Providers → Add provider → OpenID Connect
   - Alias: `naver`
   - Authorization URL: `https://nid.naver.com/oauth2.0/authorize`
   - Token URL: `https://nid.naver.com/oauth2.0/token`

## 프론트엔드 연동

### React/Vite 예시

```bash
npm install keycloak-js
```

```typescript
// src/keycloak.ts
import Keycloak from 'keycloak-js';

export const keycloak = new Keycloak({
  url: 'http://localhost:8080',
  realm: 'bsai',
  clientId: 'bsai-web',
});

// src/main.tsx
keycloak.init({
  onLoad: 'check-sso',
  pkceMethod: 'S256',
}).then((authenticated) => {
  if (authenticated) {
    console.log('User is authenticated');
  }
});
```

### API 호출 시 토큰 전달

```typescript
const response = await fetch('/api/v1/sessions', {
  headers: {
    'Authorization': `Bearer ${keycloak.token}`,
  },
});
```

## Realm 설정 내보내기

설정 변경 후 JSON으로 내보내기:

```bash
# Keycloak 컨테이너에서 실행
/opt/keycloak/bin/kc.sh export --realm bsai --dir /opt/keycloak/data/export
```

## 프로덕션 체크리스트

- [ ] HTTPS 설정 (`KC_HOSTNAME_STRICT_HTTPS=true`)
- [ ] Admin 비밀번호 변경
- [ ] 클라이언트 시크릿 변경
- [ ] Redirect URI를 프로덕션 도메인으로 변경
- [ ] 데이터베이스 분리 (전용 DB 사용)
- [ ] Brute force protection 설정 확인
