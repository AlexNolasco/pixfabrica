import { useEffect, useMemo } from 'react'
import { Check, ChevronDown } from 'lucide-react'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { useT, type TranslationKey } from '@/lib/i18n'
import { findFamilyEntry, previewUrlForWeight } from '@/lib/fonts'
import {
  FONT_ROLE_GROUPS,
  FONT_ROLES,
  previewFontSizePx,
  roleLabelKey,
  type FontRole,
} from '@/lib/typography'
import { useProjectStore } from '@/store/projectStore'

function FontFaceLoader({ urls }: { urls: string[] }) {
  useEffect(() => {
    if (urls.length === 0) return
    const style = document.createElement('style')
    const rules = urls.map((url) => {
      const family = `pf-role-${url.replace(/\W/g, '')}`
      return `@font-face{font-family:"${family}";src:url("${url}") format("woff2");font-display:swap;}`
    })
    style.textContent = rules.join('')
    document.head.appendChild(style)
    return () => {
      style.remove()
    }
  }, [urls])
  return null
}

function RolePreviewSwatch({
  role,
  typography,
  fontCatalog,
  panelWidth = 200,
}: {
  role: FontRole
  typography: ReturnType<typeof useProjectStore.getState>['typography']
  fontCatalog: ReturnType<typeof useProjectStore.getState>['fontCatalog']
  panelWidth?: number
}) {
  const spec = typography[role]
  if (!spec) return null
  const entry = findFamilyEntry(fontCatalog, spec.family)
  const previewUrl = previewUrlForWeight(entry, spec.weight)
  // Keep role swatches stable when project resolution changes.
  const px = previewFontSizePx(spec, panelWidth, panelWidth)
  const faceId = previewUrl ? `pf-role-${previewUrl.replace(/\W/g, '')}` : spec.family

  return (
    <span
      className="shrink-0 truncate rounded border border-border/50 bg-background/60 px-1.5 py-0.5 text-foreground"
      style={{
        fontFamily: previewUrl
          ? `"${faceId}", ${spec.family}, sans-serif`
          : `${spec.family}, sans-serif`,
        fontWeight: spec.weight,
        fontSize: px,
        lineHeight: 1.1,
        minWidth: 28,
        maxWidth: 72,
        textAlign: 'center',
      }}
    >
      Ag
    </span>
  )
}

const triggerClass =
  'flex w-full items-center gap-2 rounded border border-border bg-background px-2 py-1 text-xs outline-none focus:border-primary/60 hover:bg-muted/30'

export function ParamTypographyRole({
  value,
  options,
  onChange,
}: {
  value: string
  options: string[]
  onChange: (v: string) => void
}) {
  const t = useT()
  const typography = useProjectStore((s) => s.typography)
  const fontCatalog = useProjectStore((s) => s.fontCatalog)

  const roles = options.length > 0 ? options : [...FONT_ROLES]
  const allowed = useMemo(() => new Set(roles), [roles])
  const selected = (allowed.has(value) ? value : roles[0] ?? 'body_medium') as FontRole

  const groupedRoles = useMemo(() => {
    const grouped = Object.entries(FONT_ROLE_GROUPS)
      .map(([group, groupRoles]) => ({
        group,
        roles: groupRoles.filter((r) => allowed.has(r)),
      }))
      .filter((g) => g.roles.length > 0)
    const inGroup = new Set(grouped.flatMap((g) => g.roles))
    const ungrouped = roles.filter((r) => !inGroup.has(r as FontRole))
    if (ungrouped.length > 0) {
      grouped.push({ group: 'other', roles: ungrouped as FontRole[] })
    }
    return grouped
  }, [allowed, roles])

  const previewUrls = useMemo(() => {
    const urls = new Set<string>()
    for (const role of roles) {
      const spec = typography[role as FontRole]
      if (!spec) continue
      const entry = findFamilyEntry(fontCatalog, spec.family)
      const url = previewUrlForWeight(entry, spec.weight)
      if (url) urls.add(url)
    }
    return [...urls]
  }, [fontCatalog, roles, typography])

  const groupLabel = (group: string) =>
    group === 'other' ? t('optgroup_other' as TranslationKey) : t(`typography_group_${group}` as TranslationKey)

  return (
    <div className="flex flex-col gap-1">
      <FontFaceLoader urls={previewUrls} />
      <DropdownMenu>
        <DropdownMenuTrigger className={triggerClass}>
          <span className="min-w-0 flex-1 truncate text-left text-foreground">
            {t(roleLabelKey(selected))}
          </span>
          <RolePreviewSwatch
            role={selected}
            typography={typography}
            fontCatalog={fontCatalog}
            panelWidth={160}
          />
          <ChevronDown className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
        </DropdownMenuTrigger>
        <DropdownMenuContent className="max-h-64 min-w-[14rem]" align="start">
          {groupedRoles.map(({ group, roles: groupRoles }, idx) => (
            <DropdownMenuGroup key={group}>
              {idx > 0 ? <div className="my-1 h-px bg-border" /> : null}
              <DropdownMenuLabel className="text-[10px] uppercase tracking-wide">
                {groupLabel(group)}
              </DropdownMenuLabel>
              {groupRoles.map((role) => {
                const isSelected = role === selected
                return (
                  <DropdownMenuItem
                    key={role}
                    className="flex items-center justify-between gap-2 py-1.5 text-xs"
                    onClick={() => onChange(role)}
                  >
                    <span className="flex min-w-0 flex-1 items-center gap-1.5">
                      {isSelected ? (
                        <Check className="h-3.5 w-3.5 shrink-0 text-primary" />
                      ) : (
                        <span className="w-3.5 shrink-0" />
                      )}
                      <span className="truncate">{t(roleLabelKey(role))}</span>
                    </span>
                    <RolePreviewSwatch
                      role={role}
                      typography={typography}
                      fontCatalog={fontCatalog}
                      panelWidth={160}
                    />
                  </DropdownMenuItem>
                )
              })}
            </DropdownMenuGroup>
          ))}
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  )
}
