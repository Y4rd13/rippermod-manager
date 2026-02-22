import { useCallback, useState } from "react";

interface ContextMenuState<T> {
  visible: boolean;
  position: { x: number; y: number };
  data: T | null;
}

export function useContextMenu<T>() {
  const [menuState, setMenuState] = useState<ContextMenuState<T>>({
    visible: false,
    position: { x: 0, y: 0 },
    data: null,
  });

  const openMenu = useCallback((e: React.MouseEvent, data: T) => {
    e.preventDefault();
    e.stopPropagation();
    setMenuState({ visible: true, position: { x: e.clientX, y: e.clientY }, data });
  }, []);

  const closeMenu = useCallback(() => {
    setMenuState((prev) => ({ ...prev, visible: false, data: null }));
  }, []);

  return { menuState, openMenu, closeMenu };
}
