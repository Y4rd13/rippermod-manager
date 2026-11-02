import {
  createContext,
  type ReactNode,
  type RefObject,
  useContext,
  useEffect,
  useId,
  useRef,
} from "react";
import { createPortal } from "react-dom";

import { cn } from "@/lib/utils";

interface DialogProps {
  /** Defaults to true, so callers that mount the dialog conditionally can omit it. */
  open?: boolean;
  onClose: () => void;
  /** Id of the element that titles the dialog (aria-labelledby). */
  titleId: string;
  describedById?: string;
  /** Element to focus on open; defaults to the first focusable control, then the panel. */
  initialFocusRef?: RefObject<HTMLElement | null>;
  /** Default true. Pass false while an operation runs. */
  closeOnEscape?: boolean;
  /** Runs on Escape in place of onClose, e.g. to step back inside the dialog. */
  onEscape?: () => void;
  /** Default true. */
  closeOnBackdrop?: boolean;
  /** Panel classes. */
  className?: string;
  /** Backdrop (overlay) classes; replaces the default centered overlay. */
  backdropClassName?: string;
  children: ReactNode;
}

const FOCUSABLE =
  'a[href], area[href], button:not([disabled]), input:not([disabled]):not([type="hidden"]), select:not([disabled]), textarea:not([disabled]), iframe, [contenteditable="true"], [tabindex]:not([tabindex="-1"])';

interface StackEntry {
  id: string;
  parentId: string | null;
  panel: HTMLElement;
  getOptions: () => { closeOnEscape: boolean; onEscape: () => void };
}

/** Open dialogs, bottom first. The last entry is the active one. */
const stack: StackEntry[] = [];

const ParentDialogContext = createContext<string | null>(null);

function focusableIn(panel: HTMLElement): HTMLElement[] {
  return Array.from(panel.querySelectorAll<HTMLElement>(FOCUSABLE)).filter(
    (el) => !el.hasAttribute("hidden") && !el.closest("[inert]"),
  );
}

/** Background scopes and every dialog below the top one become inert. */
function syncInert() {
  const anyOpen = stack.length > 0;
  document.querySelectorAll<HTMLElement>("[data-inert-scope]").forEach((el) => {
    if (anyOpen) el.setAttribute("inert", "");
    else el.removeAttribute("inert");
  });
  stack.forEach((entry, i) => {
    if (i === stack.length - 1) entry.panel.removeAttribute("inert");
    else entry.panel.setAttribute("inert", "");
  });
}

function handleDocumentKeyDown(e: KeyboardEvent) {
  const top = stack[stack.length - 1];
  if (!top) return;
  if (e.key === "Escape") {
    // A control inside the dialog that handles Escape itself (an inline editor) calls
    // preventDefault, and the dialog stays open.
    if (e.defaultPrevented) return;
    const { closeOnEscape, onEscape } = top.getOptions();
    if (!closeOnEscape) return;
    e.preventDefault();
    e.stopPropagation();
    onEscape();
    return;
  }
  if (e.key !== "Tab") return;
  const items = focusableIn(top.panel);
  const active = document.activeElement as HTMLElement | null;
  if (items.length === 0) {
    e.preventDefault();
    top.panel.focus();
    return;
  }
  const first = items[0];
  const last = items[items.length - 1];
  const inside = !!active && top.panel.contains(active);
  if (e.shiftKey) {
    if (!inside || active === first || active === top.panel) {
      e.preventDefault();
      last.focus();
    }
  } else if (!inside || active === last) {
    e.preventDefault();
    first.focus();
  }
}

function register(entry: StackEntry) {
  if (stack.length === 0) document.addEventListener("keydown", handleDocumentKeyDown);
  // A dialog nested in another one's React tree always sits above it. Child effects run
  // before their parent's, so a parent registering late goes below its children.
  const childIndex = stack.findIndex((e) => e.parentId === entry.id);
  if (childIndex === -1) stack.push(entry);
  else stack.splice(childIndex, 0, entry);
  syncInert();
}

function unregister(id: string) {
  const i = stack.findIndex((e) => e.id === id);
  if (i !== -1) stack.splice(i, 1);
  if (stack.length === 0) document.removeEventListener("keydown", handleDocumentKeyDown);
  syncInert();
}

/**
 * The app's only modal dialog. Renders in a portal on document.body, moves focus inside on
 * open, keeps Tab and Shift+Tab inside, closes on Escape, returns focus to the opener on
 * close, and marks every `[data-inert-scope]` element inert while open.
 */
export function Dialog({ open = true, ...rest }: DialogProps) {
  if (!open) return null;
  return <OpenDialog {...rest} />;
}

function OpenDialog({
  onClose,
  titleId,
  describedById,
  initialFocusRef,
  closeOnEscape = true,
  onEscape,
  closeOnBackdrop = true,
  className,
  backdropClassName,
  children,
}: Omit<DialogProps, "open">) {
  const id = useId();
  const parentId = useContext(ParentDialogContext);
  const panelRef = useRef<HTMLDivElement>(null);
  const pressedOnBackdrop = useRef(false);
  const options = useRef({ closeOnEscape, onEscape: onEscape ?? onClose });
  useEffect(() => {
    options.current = { closeOnEscape, onEscape: onEscape ?? onClose };
  });

  useEffect(() => {
    const panel = panelRef.current;
    if (!panel) return;
    const opener = document.activeElement as HTMLElement | null;
    register({ id, parentId, panel, getOptions: () => options.current });
    if (stack[stack.length - 1]?.id === id) {
      const target = initialFocusRef?.current ?? focusableIn(panel)[0] ?? panel;
      target.focus();
    }
    return () => {
      unregister(id);
      if (opener && opener.isConnected && opener !== document.body && !opener.closest("[inert]")) {
        opener.focus();
      }
    };
    // Registration is tied to the dialog's lifetime; the initial focus target is read once.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id, parentId]);

  return createPortal(
    <ParentDialogContext value={id}>
      <div
        className={cn(
          backdropClassName ?? "fixed inset-0 z-50 flex items-center justify-center bg-black/50",
        )}
        onMouseDown={(e) => {
          pressedOnBackdrop.current = e.target === e.currentTarget;
        }}
        onClick={(e) => {
          // A drag that starts inside the panel (e.g. selecting a path) and ends over the
          // backdrop fires its click on the backdrop: close only when the press began there.
          if (closeOnBackdrop && pressedOnBackdrop.current && e.target === e.currentTarget) {
            onClose();
          }
          pressedOnBackdrop.current = false;
          // The portal still bubbles through the React tree: keep clicks inside the dialog
          // from reaching a clickable row or card that rendered it.
          e.stopPropagation();
        }}
      >
        <div
          ref={panelRef}
          role="dialog"
          aria-modal="true"
          aria-labelledby={titleId}
          aria-describedby={describedById}
          tabIndex={-1}
          className={cn("outline-none", className)}
        >
          {children}
        </div>
      </div>
    </ParentDialogContext>,
    document.body,
  );
}
