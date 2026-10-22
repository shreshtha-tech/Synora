import type { DefaultSession } from "next-auth";

type BackendUser = { id: string; email: string; name?: string | null };

declare module "next-auth" {
  interface Session {
    idToken?: string;
    backendToken?: string;
    user: DefaultSession["user"] & { id?: string };
  }
}

declare module "next-auth/jwt" {
  interface JWT {
    id_token?: string;
    backendToken?: string;
    user?: BackendUser;
  }
}
