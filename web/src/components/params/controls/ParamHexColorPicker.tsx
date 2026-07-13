import { Pipette } from 'lucide-react'
import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { HexAlphaColorPicker, HexColorPicker } from 'react-colorful'
import { useT } from '@/lib/i18n'
import { isHexColor } from '@/lib/themeColor'
import { useColorPickStore } from '@/store/colorPickStore'

const PANEL_WIDTH = 220

function pickerColor(value: string): string {
  if (isHexColor(value)) return value
  return '#ffffff'
}

function usesAlpha(value: string): boolean {
  return /^#[0-9a-fA-F]{8}$/.test(value)
}

export function ParamHexColorPicker({
  value,
  onChange,
  open: openProp,
  onOpenChange,
  previewPick = true,
  children,
}: {
  value: string
  onChange: (hex: string) => void
  open?: boolean
  onOpenChange?: (open: boolean) => void
  previewPick?: boolean
  children: ReactNode
}) {
  const t = useT()
  const [openInternal, setOpenInternal] = useState(false)
  const open = openProp ?? openInternal
  const setOpen = onOpenChange ?? setOpenInternal

  const triggerRef = useRef<HTMLButtonElement>(null)
  const panelRef = useRef<HTMLDivElement>(null)
  const [position, setPosition] = useState({ top: 0, left: 0 })

  const picking = useColorPickStore((s) => s.active)
  const beginPick = useColorPickStore((s) => s.beginPick)
  const cancelPick = useColorPickStore((s) => s.cancelPick)

  const color = pickerColor(value)
  const Picker = usesAlpha(color) ? HexAlphaColorPicker : HexColorPicker

  useLayoutEffect(() => {
    if (!open || !triggerRef.current) return
    const rect = triggerRef.current.getBoundingClientRect()
    let left = rect.left
    if (left + PANEL_WIDTH > window.innerWidth - 8) {
      left = Math.max(8, window.innerWidth - PANEL_WIDTH - 8)
    }
    setPosition({ top: rect.bottom + 6, left })
  }, [open])

  useEffect(() => {
    if (!open) return
    const onPointerDown = (event: PointerEvent) => {
      const target = event.target as Node
      if (triggerRef.current?.contains(target)) return
      if (panelRef.current?.contains(target)) return
      setOpen(false)
    }
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false)
    }
    document.addEventListener('pointerdown', onPointerDown)
    document.addEventListener('keydown', onKeyDown)
    return () => {
      document.removeEventListener('pointerdown', onPointerDown)
      document.removeEventListener('keydown', onKeyDown)
    }
  }, [open, setOpen])

  const togglePreviewPick = () => {
    if (picking) {
      cancelPick()
      return
    }
    setOpen(false)
    beginPick((hex) => onChange(hex))
  }

  return (
    <>
      <div className="flex shrink-0 items-center gap-1">
        <button
          ref={triggerRef}
          type="button"
          title={t('param_color_open_picker')}
          aria-label={t('param_color_open_picker')}
          aria-expanded={open}
          className="shrink-0 cursor-pointer rounded border border-border outline-none hover:ring-2 hover:ring-primary/30 focus-visible:ring-2 focus-visible:ring-primary/60"
          onClick={() => setOpen(!open)}
        >
          {children}
        </button>
        {previewPick ? (
          <button
            type="button"
            title={t('param_color_pick_preview')}
            aria-label={t('param_color_pick_preview')}
            aria-pressed={picking}
            className={`flex h-6 w-6 shrink-0 items-center justify-center rounded border outline-none focus-visible:ring-2 focus-visible:ring-primary/60 ${
              picking
                ? 'border-primary bg-primary/15 text-primary ring-2 ring-primary/40'
                : 'border-border text-muted-foreground hover:bg-muted hover:text-foreground'
            }`}
            onClick={togglePreviewPick}
          >
            <Pipette className="h-3.5 w-3.5" />
          </button>
        ) : null}
      </div>
      {open
        ? createPortal(
            <div
              ref={panelRef}
              role="dialog"
              aria-label={t('param_color_open_picker')}
              className="rounded-lg border border-border bg-popover p-2.5 shadow-lg ring-1 ring-foreground/10"
              style={{
                position: 'fixed',
                top: position.top,
                left: position.left,
                width: PANEL_WIDTH,
                zIndex: 9999,
              }}
              onPointerDown={(e) => e.stopPropagation()}
            >
              <Picker
                color={color}
                onChange={onChange}
                className="hex-color-picker"
              />
            </div>,
            document.body,
          )
        : null}
    </>
  )
}
