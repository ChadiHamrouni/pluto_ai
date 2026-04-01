import { useState, useCallback } from "react";
import { login as apiLogin, logout as apiLogout, hasToken } from "../api";

/**
 * useAuth — manages login/logout state.
 *
 * Initialises from the token already in localStorage (set by api.js).
 * On login, stores tokens via api.js and flips isLoggedIn.
 * On logout, clears tokens and flips back.
 */
export function useAuth() {
  const [isLoggedIn, setIsLoggedIn] = useState(() => hasToken());
  const [loading, setLoading]       = useState(false);
  const [error, setError]           = useState(null);

  const login = useCallback(async (username, password) => {
    setLoading(true);
    setError(null);
    try {
      await apiLogin(username, password);
      setIsLoggedIn(true);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  const logout = useCallback(() => {
    apiLogout();
    setIsLoggedIn(false);
  }, []);

  return { isLoggedIn, loading, error, login, logout };
}
