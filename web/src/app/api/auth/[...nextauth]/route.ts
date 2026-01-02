import NextAuth, { AuthOptions, Account } from 'next-auth';
import { JWT } from 'next-auth/jwt';

declare module 'next-auth' {
  interface Session {
    accessToken?: string;
    error?: string;
  }
}

declare module 'next-auth/jwt' {
  interface JWT {
    accessToken?: string;
    refreshToken?: string;
    expiresAt?: number;
    error?: string;
  }
}

// Use separate URLs for internal (server-side) and external (browser) access
const KEYCLOAK_INTERNAL = process.env.KEYCLOAK_ISSUER || 'http://keycloak:8080/realms/bsai';
const KEYCLOAK_EXTERNAL = process.env.KEYCLOAK_ISSUER_EXTERNAL || 'http://localhost:8080/realms/bsai';

async function refreshAccessToken(token: JWT): Promise<JWT> {
  try {
    const url = `${KEYCLOAK_INTERNAL}/protocol/openid-connect/token`;
    const response = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded',
      },
      body: new URLSearchParams({
        client_id: process.env.KEYCLOAK_ID!,
        client_secret: process.env.KEYCLOAK_SECRET!,
        grant_type: 'refresh_token',
        refresh_token: token.refreshToken!,
      }),
    });

    const refreshedTokens = await response.json();

    if (!response.ok) {
      throw refreshedTokens;
    }

    return {
      ...token,
      accessToken: refreshedTokens.access_token,
      refreshToken: refreshedTokens.refresh_token ?? token.refreshToken,
      expiresAt: Math.floor(Date.now() / 1000) + refreshedTokens.expires_in,
    };
  } catch (error) {
    console.error('Error refreshing access token:', error);
    return {
      ...token,
      error: 'RefreshAccessTokenError',
    };
  }
}

export const authOptions: AuthOptions = {
  debug: process.env.NODE_ENV === 'development',
  providers: [
    {
      id: 'keycloak',
      name: 'Keycloak',
      type: 'oauth',
      clientId: process.env.KEYCLOAK_ID!,
      clientSecret: process.env.KEYCLOAK_SECRET!,
      // Issuer for OIDC validation (use external since that's what Keycloak returns)
      issuer: KEYCLOAK_EXTERNAL,
      // Use external URL for browser redirects
      authorization: {
        url: `${KEYCLOAK_EXTERNAL}/protocol/openid-connect/auth`,
        params: { scope: 'openid email profile' },
      },
      // Use internal URL for server-side token exchange
      token: `${KEYCLOAK_INTERNAL}/protocol/openid-connect/token`,
      userinfo: `${KEYCLOAK_INTERNAL}/protocol/openid-connect/userinfo`,
      jwks_endpoint: `${KEYCLOAK_INTERNAL}/protocol/openid-connect/certs`,
      // Use PKCE with S256 (required by Keycloak)
      checks: ['pkce', 'state'],
      idToken: true,
      profile(profile) {
        return {
          id: profile.sub,
          name: profile.name || profile.preferred_username,
          email: profile.email,
          image: profile.picture,
        };
      },
    },
  ],
  callbacks: {
    async jwt({ token, account }: { token: JWT; account: Account | null }) {
      // Initial sign in
      if (account) {
        return {
          ...token,
          accessToken: account.access_token,
          refreshToken: account.refresh_token,
          expiresAt: account.expires_at,
        };
      }

      // Return previous token if not expired
      if (token.expiresAt && Date.now() < token.expiresAt * 1000) {
        return token;
      }

      // Token expired, try to refresh
      return refreshAccessToken(token);
    },
    async session({ session, token }) {
      session.accessToken = token.accessToken;
      session.error = token.error;
      return session;
    },
  },
  pages: {
    signIn: '/login',
    error: '/login',
  },
  session: {
    strategy: 'jwt',
  },
};

const handler = NextAuth(authOptions);

export { handler as GET, handler as POST };
