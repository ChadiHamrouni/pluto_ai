import { useState, useRef, useCallback } from "react";
import { searchContent } from "../api";

const DEBOUNCE_MS = 300;
const MIN_QUERY_LEN = 2;

export function useContentSearch() {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const timerRef = useRef(null);

  const handleQueryChange = useCallback((newQuery) => {
    setQuery(newQuery);
    setError(null);

    if (timerRef.current) clearTimeout(timerRef.current);

    // Fire immediately for bare type prefixes (e.g. "-note", "-pdf")
    // otherwise require MIN_QUERY_LEN chars after stripping the prefix
    const stripped = newQuery.replace(/^-\w+\s*/, "").trim();
    const isBarePrefix = /^-\w+$/.test(newQuery.trim());
    if (!newQuery || (!isBarePrefix && stripped.length < MIN_QUERY_LEN)) {
      setResults([]);
      setLoading(false);
      return;
    }

    setLoading(true);
    timerRef.current = setTimeout(async () => {
      try {
        const data = await searchContent(newQuery.trim());
        setResults(data.results ?? []);
      } catch (err) {
        setError(err.message);
        setResults([]);
      } finally {
        setLoading(false);
      }
    }, DEBOUNCE_MS);
  }, []);

  const reset = useCallback(() => {
    if (timerRef.current) clearTimeout(timerRef.current);
    setQuery("");
    setResults([]);
    setLoading(false);
    setError(null);
  }, []);

  return { query, results, loading, error, handleQueryChange, reset };
}
