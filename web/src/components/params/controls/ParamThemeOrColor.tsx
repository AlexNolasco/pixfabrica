import { useEffect, useState } from 'react'
import { ParamHexColorPicker } from '@/components/params/controls/ParamHexColorPicker'
import {
  COLOR_TOKENS,
  isColorToken,
  isHexColor,
  normalizeHexInput,
  resolveSwatch,
  type ColorTokenName,
} from '@/lib/themeColor'
import { useT } from '@/lib/i18n'

const selectClass =
  'w-full rounded border border-border bg-background px-2 py-1 text-xs outline-none focus:border-primary/60'

export function ParamThemeOrColor({
  value,
  nullable,
  jobTheme,
  onChange,
}: {
  value: string | null
  nullable: boolean
  jobTheme?: Record<string, string>
  onChange: (v: string | null) => void
}) {
  const t = useT()

  const mode: 'none' | 'token' | 'hex' =
    value === null || value === undefined || value === ''
      ? 'none'
      : isHexColor(value)
        ? 'hex'
        : 'token'

  const hexValue = isHexColor(value) ? value : '#ffffff'
  const swatch = value != null && value !== '' ? resolveSwatch(value, jobTheme) : '#888'

  const [hexDraft, setHexDraft] = useState<string | null>(null)
  const [pickerOpen, setPickerOpen] = useState(false)
  useEffect(() => {
    setHexDraft(null)
  }, [value])

  const hexInputValue = hexDraft ?? hexValue

  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex items-center gap-2">
        {mode === 'hex' ? (
          <ParamHexColorPicker
            value={hexValue}
            open={pickerOpen}
            onOpenChange={setPickerOpen}
            onChange={onChange}
          >
            <span
              className="block h-6 w-6 rounded"
              style={{ backgroundColor: swatch }}
            />
          </ParamHexColorPicker>
        ) : (
          <span
            className="h-6 w-6 shrink-0 rounded border border-border"
            style={{ backgroundColor: swatch }}
          />
        )}
        <select
          className={selectClass}
          value={mode === 'hex' ? '__hex__' : mode === 'none' ? '' : value ?? ''}
          onChange={(e) => {
            const v = e.target.value
            if (v === '') onChange(nullable ? null : COLOR_TOKENS[0])
            else if (v === '__hex__') {
              onChange('#ffffff')
              setPickerOpen(true)
            } else onChange(v)
          }}
        >
          {nullable ? <option value="">—</option> : null}
          {COLOR_TOKENS.map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
          <option value="__hex__">{t('param_color_custom_hex')}</option>
        </select>
      </div>
      {(mode === 'hex' || (value && isHexColor(value))) && (
        <input
          type="text"
          className="w-full rounded border border-border bg-background px-2 py-1 font-mono text-xs outline-none focus:border-primary/60"
          value={hexInputValue}
          placeholder="#RRGGBB"
          onChange={(e) => setHexDraft(e.target.value)}
          onBlur={() => {
            if (hexDraft == null) return
            const normalized = normalizeHexInput(hexDraft)
            if (normalized) onChange(normalized)
            setHexDraft(null)
          }}
          onKeyDown={(e) => {
            if (e.key === 'Enter') {
              e.currentTarget.blur()
            }
          }}
        />
      )}
      {mode === 'token' && isColorToken(value) && (
        <div className="flex flex-wrap gap-1">
          {COLOR_TOKENS.map((t) => (
            <button
              key={t}
              type="button"
              title={t}
              className={`h-5 w-5 rounded border ${
                value === t ? 'ring-2 ring-primary' : 'border-border'
              }`}
              style={{ backgroundColor: resolveSwatch(t, jobTheme) }}
              onClick={() => onChange(t as ColorTokenName)}
            />
          ))}
        </div>
      )}
    </div>
  )
}
