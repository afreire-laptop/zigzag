import { useCallback, useEffect, useState } from "react";

export type Surface = "brief" | "review";

const read = (): Surface => (window.location.hash === "#review" ? "review" : "brief");

/** The two surfaces are addressed by the URL hash, so reload and back/forward keep the place. */
export function useSurface(): [Surface, (s: Surface) => void] {
  const [surface, setSurface] = useState<Surface>(read);
  useEffect(() => {
    const onHash = () => setSurface(read());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);
  const go = useCallback((s: Surface) => {
    window.location.hash = s;
  }, []);
  return [surface, go];
}
