import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it } from "vitest";
import { Modal } from "@/components/ui";

/** A page that opens a modal; its onClose is a fresh function on every render, as in the real pages. */
function Page({ withInput = false }: { withInput?: boolean }) {
  const [open, setOpen] = useState(false);
  const [text, setText] = useState("");
  return (
    <div>
      <button onClick={() => setOpen(true)}>Open</button>
      <button>Other control behind the dialog</button>
      {open && (
        <Modal title="Edit value" onClose={() => setOpen(false)}>
          {withInput && <input aria-label="Value" value={text} onChange={(e) => setText(e.target.value)} />}
          <button>Save</button>
        </Modal>
      )}
    </div>
  );
}

const tab = (el: Element, shift = false) => fireEvent.keyDown(el, { key: "Tab", shiftKey: shift });

describe("Modal keyboard behaviour", () => {
  it("moves focus into the dialog and gives it back to the opener on Escape", () => {
    render(<Page />);
    const opener = screen.getByText("Open");
    opener.focus();
    fireEvent.click(opener);
    expect(screen.getByRole("dialog")).toHaveFocus();
    fireEvent.keyDown(document.activeElement ?? document.body, { key: "Escape" });
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(opener).toHaveFocus();
  });

  it("gives focus back to the opener on the Close button too", () => {
    render(<Page />);
    const opener = screen.getByText("Open");
    opener.focus();
    fireEvent.click(opener);
    fireEvent.click(screen.getByLabelText("Close"));
    expect(opener).toHaveFocus();
  });

  it("keeps the caret in a field while the page re-renders on every keystroke", () => {
    render(<Page withInput />);
    const opener = screen.getByText("Open");
    opener.focus();
    fireEvent.click(opener);
    const input = screen.getByLabelText("Value");
    input.focus();
    for (const ch of ["a", "b", "c"]) {
      fireEvent.change(input, { target: { value: (input as HTMLInputElement).value + ch } });
      expect(input).toHaveFocus(); // a re-render must not steal focus back to the dialog or the opener
    }
    expect((input as HTMLInputElement).value).toBe("abc");
  });

  it("still returns focus to the original opener after the page re-rendered many times", () => {
    render(<Page withInput />);
    const opener = screen.getByText("Open");
    opener.focus();
    fireEvent.click(opener);
    const input = screen.getByLabelText("Value");
    for (const ch of "hello") fireEvent.change(input, { target: { value: (input as HTMLInputElement).value + ch } });
    fireEvent.click(screen.getByLabelText("Close"));
    expect(opener).toHaveFocus();
  });

  it("keeps Tab inside the dialog: the last control wraps to the first, and back", () => {
    render(<Page withInput />);
    fireEvent.click(screen.getByText("Open"));
    const close = screen.getByLabelText("Close");
    const save = screen.getByText("Save");
    save.focus();
    tab(save); // forward from the last control
    expect(close).toHaveFocus();
    tab(close, true); // backward from the first
    expect(save).toHaveFocus();
  });

  it("pulls focus back in if it is somewhere behind the dialog when Tab is pressed", () => {
    render(<Page withInput />);
    fireEvent.click(screen.getByText("Open"));
    const behind = screen.getByText("Other control behind the dialog");
    behind.focus();
    tab(behind);
    expect(screen.getByRole("dialog").contains(document.activeElement)).toBe(true);
  });

  it("closes once on Escape, not once per re-render", () => {
    let closes = 0;
    function Counting() {
      const [n, setN] = useState(0);
      return (
        <div>
          <button onClick={() => setN(n + 1)}>Rerender</button>
          <Modal title="t" onClose={() => (closes += 1)}>
            <span>{n}</span>
          </Modal>
        </div>
      );
    }
    render(<Counting />);
    for (let i = 0; i < 3; i++) fireEvent.click(screen.getByText("Rerender"));
    fireEvent.keyDown(document.body, { key: "Escape" });
    expect(closes).toBe(1);
  });
});
