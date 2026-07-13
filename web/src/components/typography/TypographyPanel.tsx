import { useEffect, useMemo, useRef, useState } from 'react'
import { ChevronDown, Type, Upload } from 'lucide-react'
import { useProjectStore } from '@/store/projectStore'
import { useT, type TranslationKey } from '@/lib/i18n'
import {
  FONT_UPLOAD_ACCEPT,
  apiUploadFont,
  pollFontJob,
} from '@/lib/fontInstall'
import {
  FONT_ROLE_GROUPS,
  previewFontSizePx,
  roleLabelKey,
  sansFamilyFromPalette,
  monoFamilyFromPalette,
  type FontSpec,
} from '@/lib/typography'
import { findFamilyEntry, previewUrlForWeight } from '@/lib/fonts'

function closedGroups(): Record<string, boolean> {
  return Object.fromEntries(Object.keys(FONT_ROLE_GROUPS).map((g) => [g, false]))
}

function FontFaceLoader({ urls }: { urls: string[] }) {
  useEffect(() => {
    if (urls.length === 0) return
    const style = document.createElement('style')
    const rules = urls.map((url) => {
      const family = `pf-preview-${url.replace(/\W/g, '')}`
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

function RolePreview({
  spec,
  previewUrl,
}: {
  spec: FontSpec
  previewUrl?: string
}) {
  const px = previewFontSizePx(spec, 240, 240)
  const faceId = previewUrl ? `pf-preview-${previewUrl.replace(/\W/g, '')}` : spec.family
  return (
    <div
      className="truncate rounded border border-border/50 bg-background/40 px-2 py-0.5 text-foreground"
      style={{
        fontFamily: previewUrl
          ? `"${faceId}", ${spec.family}, sans-serif`
          : `${spec.family}, sans-serif`,
        fontWeight: spec.weight,
        fontSize: px,
        lineHeight: 1.1,
      }}
    >
      Ag
    </div>
  )
}

export function TypographyPanel() {
  const t = useT()
  const typography = useProjectStore((s) => s.typography)
  const fontCatalog = useProjectStore((s) => s.fontCatalog)
  const fontCatalogFallback = useProjectStore((s) => s.fontCatalogFallback)
  const setSansFamily = useProjectStore((s) => s.setSansFamily)
  const setMonoFamily = useProjectStore((s) => s.setMonoFamily)
  const setRoleTypography = useProjectStore((s) => s.setRoleTypography)
  const fetchFontCatalog = useProjectStore((s) => s.fetchFontCatalog)
  const appendEventLog = useProjectStore((s) => s.appendEventLog)
  const isPlaying = useProjectStore((s) => s.isPlaying)

  const fileInputRef = useRef<HTMLInputElement>(null)
  const [licenseAck, setLicenseAck] = useState(false)
  const [installing, setInstalling] = useState(false)

  const [sectionOpen, setSectionOpen] = useState(false)
  const [openGroups, setOpenGroups] = useState(closedGroups)
  const [expandedRoles, setExpandedRoles] = useState<Record<string, boolean>>({})

  const sansFamily = sansFamilyFromPalette(typography)
  const monoFamily = monoFamilyFromPalette(typography)

  const sansOptions = fontCatalog.filter((f) => f.category === 'sans')
  const monoOptions = fontCatalog.filter((f) => f.category === 'mono')

  const previewUrls = useMemo(() => {
    if (!sectionOpen) return []
    const urls = new Set<string>()
    for (const role of Object.values(FONT_ROLE_GROUPS).flat()) {
      const spec = typography[role]
      const entry = findFamilyEntry(fontCatalog, spec.family)
      const url = previewUrlForWeight(entry, spec.weight)
      if (url) urls.add(url)
    }
    return [...urls]
  }, [fontCatalog, sectionOpen, typography])

  const toggleGroup = (name: string) =>
    setOpenGroups((s) => ({ ...s, [name]: !s[name] }))

  const toggleRole = (role: string) =>
    setExpandedRoles((s) => ({ ...s, [role]: !s[role] }))

  const collapseAll = () => {
    setOpenGroups(closedGroups())
    setExpandedRoles({})
  }

  const handleInstallClick = () => {
    if (installing || isPlaying || !licenseAck) return
    fileInputRef.current?.click()
  }

  const handleInstallFile = async (file: File | undefined) => {
    if (!file || installing || isPlaying || !licenseAck) return
    setInstalling(true)
    try {
      const { job_id: jobId } = await apiUploadFont(file)
      const job = await pollFontJob(jobId)
      if (job.status === 'failed') {
        appendEventLog(
          'error',
          job.error
            ? `${t('left_typography_install_failed')}: ${job.error}`
            : t('left_typography_install_failed'),
        )
        return
      }
      await fetchFontCatalog()
      const names = job.families.join(', ')
      appendEventLog(
        'info',
        names
          ? `${t('left_typography_install_success')}: ${names}`
          : t('left_typography_install_success'),
      )
      for (const warning of job.warnings) {
        appendEventLog('warn', warning)
      }
    } catch (err) {
      appendEventLog(
        'error',
        err instanceof Error
          ? `${t('left_typography_install_failed')}: ${err.message}`
          : t('left_typography_install_failed'),
      )
    } finally {
      setInstalling(false)
      if (fileInputRef.current) fileInputRef.current.value = ''
    }
  }

  const groupLabel = (group: string) => t(`typography_group_${group}` as TranslationKey)

  return (
    <section className="flex flex-col shrink-0 border-b border-border">
      <FontFaceLoader urls={previewUrls} />
      <div className="flex items-center gap-1 px-3 py-2 select-none">
        <button
          type="button"
          className="flex flex-1 items-center gap-1.5 min-w-0 text-[11px] font-semibold text-muted-foreground uppercase tracking-wider hover:text-foreground"
          onClick={() => setSectionOpen((open) => !open)}
        >
          <Type className="w-3 h-3 shrink-0" />
          <span className="truncate">{t('left_typography')}</span>
          <ChevronDown
            className={`w-3 h-3 shrink-0 transition-transform ${sectionOpen ? 'rotate-0' : '-rotate-90'}`}
          />
        </button>
        {sectionOpen ? (
          <button
            type="button"
            className="shrink-0 rounded px-1.5 py-0.5 text-[10px] text-muted-foreground hover:bg-muted/50 hover:text-foreground"
            onClick={collapseAll}
          >
            {t('left_typography_collapse_all')}
          </button>
        ) : null}
      </div>
      {sectionOpen ? (
        <>
          {fontCatalogFallback ? (
            <p className="px-3 pb-1 text-[10px] text-amber-600 dark:text-amber-400">
              {t('left_typography_catalog_fallback')}
            </p>
          ) : null}
          <fieldset
            disabled={isPlaying}
            className={`px-3 pb-3 flex flex-col gap-2 ${isPlaying ? 'opacity-40' : ''}`}
          >
            <label className="flex flex-col gap-0.5">
              <span className="text-muted-foreground">{t('left_typography_sans')}</span>
              <select
                className="rounded border border-border bg-muted/50 px-1.5 py-0.5 text-xs text-foreground outline-none focus:border-primary/60"
                value={sansFamily}
                onChange={(e) => setSansFamily(e.target.value)}
              >
                {sansOptions.map((f) => (
                  <option key={f.id} value={f.family}>
                    {f.label}
                  </option>
                ))}
              </select>
            </label>
            <label className="flex flex-col gap-0.5">
              <span className="text-muted-foreground">{t('left_typography_mono')}</span>
              <select
                className="rounded border border-border bg-muted/50 px-1.5 py-0.5 text-xs text-foreground outline-none focus:border-primary/60"
                value={monoFamily}
                onChange={(e) => setMonoFamily(e.target.value)}
              >
                {monoOptions.map((f) => (
                  <option key={f.id} value={f.family}>
                    {f.label}
                  </option>
                ))}
              </select>
            </label>

            <div className="flex flex-col gap-1.5 rounded border border-border/50 bg-muted/10 px-2 py-2">
              <label className="flex items-start gap-2 text-[10px] text-muted-foreground">
                <input
                  type="checkbox"
                  className="mt-0.5"
                  checked={licenseAck}
                  onChange={(e) => setLicenseAck(e.target.checked)}
                  disabled={installing || isPlaying}
                />
                <span>{t('left_typography_install_license')}</span>
              </label>
              <input
                ref={fileInputRef}
                type="file"
                accept={FONT_UPLOAD_ACCEPT}
                className="hidden"
                disabled={installing || isPlaying || !licenseAck}
                onChange={(e) => void handleInstallFile(e.target.files?.[0])}
              />
              <button
                type="button"
                className="inline-flex items-center justify-center gap-1.5 rounded border border-border bg-background px-2 py-1 text-[11px] text-foreground hover:bg-muted/40 disabled:opacity-40"
                disabled={installing || isPlaying || !licenseAck}
                onClick={handleInstallClick}
              >
                <Upload className="h-3 w-3 shrink-0" />
                {installing ? t('left_typography_installing') : t('left_typography_install')}
              </button>
            </div>

            {Object.entries(FONT_ROLE_GROUPS).map(([group, roles]) => (
              <div key={group} className="flex flex-col gap-1">
                <button
                  type="button"
                  className="flex items-center justify-between text-[10px] font-semibold uppercase text-muted-foreground hover:text-foreground"
                  onClick={() => toggleGroup(group)}
                >
                  {groupLabel(group)}
                  <ChevronDown
                    className={`w-3 h-3 transition-transform ${openGroups[group] ? 'rotate-0' : '-rotate-90'}`}
                  />
                </button>
                {openGroups[group]
                  ? roles.map((role) => {
                      const spec = typography[role]
                      const entry = findFamilyEntry(fontCatalog, spec.family)
                      const previewUrl = previewUrlForWeight(entry, spec.weight)
                      const expanded = expandedRoles[role]
                      return (
                        <div
                          key={role}
                          className="rounded border border-border/40 bg-muted/20 px-2 py-1.5"
                        >
                          <button
                            type="button"
                            className="flex w-full items-center justify-between gap-2 text-left"
                            onClick={() => toggleRole(role)}
                          >
                            <span className="text-[11px] text-foreground truncate">
                              {t(roleLabelKey(role))}
                            </span>
                            <ChevronDown
                              className={`w-3 h-3 shrink-0 text-muted-foreground transition-transform ${expanded ? 'rotate-180' : ''}`}
                            />
                          </button>
                          <RolePreview spec={spec} previewUrl={previewUrl} />
                          {expanded ? (
                            <div className="mt-2 flex flex-col gap-1.5">
                              <label className="flex items-center justify-between gap-2 text-[10px]">
                                <span className="text-muted-foreground">
                                  {t('left_typography_weight')}
                                </span>
                                <input
                                  type="number"
                                  min={100}
                                  max={900}
                                  step={100}
                                  className="w-16 rounded border border-border bg-muted/50 px-1 py-0.5 text-right"
                                  value={spec.weight}
                                  onChange={(e) =>
                                    setRoleTypography(role, { weight: Number(e.target.value) })
                                  }
                                />
                              </label>
                              <label className="flex items-center justify-between gap-2 text-[10px]">
                                <span className="text-muted-foreground">
                                  {t('left_typography_size')}
                                </span>
                                <input
                                  type="number"
                                  min={1}
                                  step={0.5}
                                  className="w-16 rounded border border-border bg-muted/50 px-1 py-0.5 text-right"
                                  value={spec.size}
                                  onChange={(e) =>
                                    setRoleTypography(role, { size: Number(e.target.value) })
                                  }
                                />
                              </label>
                            </div>
                          ) : null}
                        </div>
                      )
                    })
                  : null}
              </div>
            ))}
          </fieldset>
        </>
      ) : null}
    </section>
  )
}
