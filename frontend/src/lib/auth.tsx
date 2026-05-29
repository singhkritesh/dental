import {
  createContext,
  type ReactNode,
  useContext,
  useEffect,
  useState
} from "react";

import { api, ApiError, clearAuthToken, getAuthToken, setAuthToken } from "./api";
import type { AuthBootstrapResponse, UserInfo } from "./types";

type AuthContextValue = {
  loading: boolean;
  bootstrap: AuthBootstrapResponse | null;
  user: UserInfo | null;
  login: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  register: (username: string, password: string, role?: "admin" | "staff") => Promise<void>;
  refreshMe: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [loading, setLoading] = useState(true);
  const [bootstrap, setBootstrap] = useState<AuthBootstrapResponse | null>(null);
  const [user, setUser] = useState<UserInfo | null>(null);

  useEffect(() => {
    let active = true;
    async function initialize() {
      setLoading(true);
      try {
        const bootstrapStatus = await api.getAuthBootstrap();
        if (!active) {
          return;
        }
        setBootstrap(bootstrapStatus);

        const existingToken = getAuthToken();
        if (!existingToken) {
          setUser(null);
          return;
        }
        const me = await api.me();
        if (active) {
          setUser(me);
        }
      } catch {
        clearAuthToken();
        if (active) {
          setUser(null);
        }
      } finally {
        if (active) {
          setLoading(false);
        }
      }
    }
    void initialize();
    return () => {
      active = false;
    };
  }, []);

  async function refreshMe() {
    const me = await api.me();
    setUser(me);
  }

  async function login(username: string, password: string) {
    const response = await api.login({ username, password });
    setAuthToken(response.token);
    setUser(response.user);
    const bootstrapStatus = await api.getAuthBootstrap();
    setBootstrap(bootstrapStatus);
  }

  async function logout() {
    try {
      await api.logout();
    } catch {
      // local cleanup still required
    } finally {
      clearAuthToken();
      setUser(null);
    }
  }

  async function register(username: string, password: string, role?: "admin" | "staff") {
    await api.register({ username, password, role });
    const bootstrapStatus = await api.getAuthBootstrap();
    setBootstrap(bootstrapStatus);

    try {
      await login(username, password);
    } catch (error) {
      if (error instanceof ApiError) {
        throw error;
      }
      throw new Error("Registration succeeded but auto-login failed.");
    }
  }

  return (
    <AuthContext.Provider
      value={{
        loading,
        bootstrap,
        user,
        login,
        logout,
        register,
        refreshMe
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const value = useContext(AuthContext);
  if (!value) {
    throw new Error("useAuth must be used inside AuthProvider");
  }
  return value;
}
