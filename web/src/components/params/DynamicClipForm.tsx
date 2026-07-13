import { useCallback, useMemo } from 'react'
import { listInvalidParamFields } from '@/lib/clipParamsImport'
import { listAudioBusNames } from '@/lib/audioBuses'
import { commitClipParams } from '@/lib/paramCommit'
import { coerceParamValue } from '@/lib/paramValidation'
import {
  type ControlSpec,
  type ClipCatalogDetail,
  TIMING_SECTION_ID,
  isImmediateControlKind,
} from '@/lib/catalogDetail'
import { ParamField } from '@/components/params/ParamField'
import { ParamAnchorSlider } from '@/components/params/controls/ParamAnchorSlider'
import { ParamRotationSlider } from '@/components/params/controls/ParamRotationSlider'
import { ParamColorList } from '@/components/params/controls/ParamColorList'
import { ParamColorStopList } from '@/components/params/controls/ParamColorStopList'
import { ParamFile } from '@/components/params/controls/ParamFile'
import { ParamNumber } from '@/components/params/controls/ParamNumber'
import { ParamSegmentedEnum } from '@/components/params/controls/ParamSegmentedEnum'
import { ParamSelect } from '@/components/params/controls/ParamSelect'
import { ParamSlider } from '@/components/params/controls/ParamSlider'
import { ParamText } from '@/components/params/controls/ParamText'
import { ParamThemeOrColor } from '@/components/params/controls/ParamThemeOrColor'
import { ParamToggle } from '@/components/params/controls/ParamToggle'
import { ParamTypographyRole } from '@/components/params/controls/ParamTypographyRole'
import { ParamCameraOrbit } from '@/components/params/controls/ParamCameraOrbit'
import { ParamUnknown } from '@/components/params/controls/ParamUnknown'
import { useProjectStore } from '@/store/projectStore'
import { uploadMaxBytes } from '@/lib/serverConfig'
import {
  controlUsesImageAlignPresets,
  stdImageAlignPresetOffsets,
} from '@/lib/stdImageAlign'
import { clearedStockAttributionForField } from '@/lib/stockProvenance'
import { useStockPickerStore } from '@/store/stockPickerStore'
import type { StockParamApplyResult } from '@/store/stockPickerStore'

function isStockBrowseFileControl(control: ControlSpec): boolean {
  return control.kind === 'file' && control.stock_browse === true
}

function isStockAttributionControl(field: string, control: ControlSpec): boolean {
  if (control.kind === 'textarea' && control.read_only) {
    if (typeof control.stock_source_field === 'string') return true
    if (field.endsWith('_attribution') || field === 'source_attribution') return true
  }
  return false
}

function orbitElevationField(azimuthField: string): string {
  return azimuthField.endsWith('_azimuth')
    ? azimuthField.replace(/_azimuth$/, '_elevation')
    : 'camera_elevation'
}

function orbitVariant(control: ControlSpec, azimuthField: string): 'camera' | 'light' {
  if (control.variant === 'light') return 'light'
  if (azimuthField.startsWith('light_')) return 'light'
  return 'camera'
}

function isTypographyRoleControl(field: string, control: ControlSpec): boolean {
  if (control.kind === 'typography_role') return true
  if (field !== 'typography_role' && !field.endsWith('_typography_role')) return false
  return control.kind === 'select' && Array.isArray(control.options)
}

export function DynamicClipForm({
  detail,
  params,
  trackId,
  clipId,
  effectId,
  trackEffectId,
  projectSettingId,
}: {
  detail: ClipCatalogDetail
  params: Record<string, unknown>
  trackId?: string
  clipId?: string
  effectId?: string
  trackEffectId?: string
  projectSettingId?: string
}) {
  const sounds = useProjectStore((s) => s.sounds)
  const projectSettings = useProjectStore((s) => s.projectSettings)
  const jobTheme = useProjectStore((s) => s.colors)
  const serverConfig = useProjectStore((s) => s.serverConfig)
  const updateClip = useProjectStore((s) => s.updateClip)
  const updateEffect = useProjectStore((s) => s.updateEffect)
  const updateTrackEffect = useProjectStore((s) => s.updateTrackEffect)
  const updateProjectSetting = useProjectStore((s) => s.updateProjectSetting)
  const pexelsAvailable = useProjectStore((s) => s.pexelsAvailable)
  const openParamPhotos = useStockPickerStore((s) => s.openParamPhotos)
  const openParamVideos = useStockPickerStore((s) => s.openParamVideos)

  const invalidFields = useMemo(
    () => new Set(listInvalidParamFields(detail, params)),
    [detail, params],
  )

  const ui = detail.ui
  const controls = (ui.controls ?? {}) as Record<string, ControlSpec>
  const sections = Array.isArray(ui.sections) ? ui.sections : []
  const busNames = listAudioBusNames(sounds, projectSettings)

  const applyField = useCallback(
    (field: string, raw: unknown, control: ControlSpec) => {
      const coerced = coerceParamValue(
        field,
        raw,
        control,
        detail.parameters_schema,
      )
      if (projectSettingId) {
        const setting = useProjectStore.getState().projectSettings.find((n) => n.id === projectSettingId)
        if (!setting) return
        updateProjectSetting(projectSettingId, {
          params: { ...setting.params, [field]: coerced },
        })
        return
      }
      if (!trackId) return
      const track = useProjectStore.getState().tracks.find((t) => t.id === trackId)
      if (!track) return
      if (trackEffectId) {
        const effect = track.effects?.find((fx) => fx.id === trackEffectId)
        if (!effect) return
        updateTrackEffect(trackId, trackEffectId, {
          params: { ...effect.params, [field]: coerced },
        })
        return
      }
      if (!clipId) return
      const clip = track.clips.find((el) => el.id === clipId)
      if (!clip) return
      if (effectId) {
        const effect = clip.effects?.find((fx) => fx.id === effectId)
        if (!effect) return
        updateEffect(trackId, clipId, effectId, {
          params: { ...effect.params, [field]: coerced },
        })
        return
      }
      if (field === 'align' && typeof coerced === 'string' && controlUsesImageAlignPresets(control)) {
        const presetOffsets = stdImageAlignPresetOffsets(coerced)
        updateClip(trackId, clipId, {
          params: presetOffsets
            ? {
                ...clip.params,
                align: coerced,
                offset_x: presetOffsets.offset_x,
                offset_y: presetOffsets.offset_y,
              }
            : { ...clip.params, [field]: coerced },
        })
        return
      }
      if (isStockBrowseFileControl(control) && coerced !== clip.params[field]) {
        updateClip(trackId, clipId, {
          params: {
            ...clip.params,
            [field]: coerced,
            ...clearedStockAttributionForField(field),
          },
        })
        return
      }
      updateClip(trackId, clipId, {
        params: { ...clip.params, [field]: coerced },
      })
    },
    [clipId, detail.parameters_schema, projectSettingId, trackId, trackEffectId, effectId, updateClip, updateEffect, updateProjectSetting, updateTrackEffect],
  )

  const applyStockField = useCallback(
    (field: string, result: StockParamApplyResult) => {
      const nextParams = {
        [field]: result.path,
        ...result.extraParams,
      }
      if (projectSettingId) {
        const setting = useProjectStore.getState().projectSettings.find((n) => n.id === projectSettingId)
        if (!setting) return
        updateProjectSetting(projectSettingId, {
          params: { ...setting.params, ...nextParams },
        })
        return
      }
      if (!trackId) return
      const track = useProjectStore.getState().tracks.find((t) => t.id === trackId)
      if (!track) return
      if (trackEffectId) {
        const effect = track.effects?.find((fx) => fx.id === trackEffectId)
        if (!effect) return
        updateTrackEffect(trackId, trackEffectId, {
          params: { ...effect.params, ...nextParams },
        })
        return
      }
      if (!clipId) return
      const clip = track.clips.find((el) => el.id === clipId)
      if (!clip) return
      if (effectId) {
        const effect = clip.effects?.find((fx) => fx.id === effectId)
        if (!effect) return
        updateEffect(trackId, clipId, effectId, {
          params: { ...effect.params, ...nextParams },
        })
        return
      }
      updateClip(trackId, clipId, {
        params: { ...clip.params, ...nextParams },
      })
    },
    [clipId, effectId, projectSettingId, trackEffectId, trackId, updateEffect, updateClip, updateProjectSetting, updateTrackEffect],
  )

  const openStockBrowse = useCallback(
    (field: string, control: ControlSpec) => {
      const target = {
        uploadContext: {
          clip_type: detail.clip_type,
          plugin_id: detail.plugin_id,
        },
        field,
        onApply: (result: StockParamApplyResult) => {
          applyStockField(field, result)
        },
      }
      if (control.upload_kind === 'video') {
        openParamVideos(target)
      } else {
        openParamPhotos(target)
      }
    },
    [applyStockField, detail.clip_type, detail.plugin_id, openParamPhotos, openParamVideos],
  )

  const setField = useCallback(
    (field: string, raw: unknown, control: ControlSpec, immediate = false) => {
      const ownerKey = projectSettingId ?? `${trackId}:${trackEffectId ?? clipId}`
      const commitKey = `${ownerKey}:${field}`
      const commitNow = immediate || isImmediateControlKind(control.kind)
      commitClipParams(commitKey, commitNow, () => applyField(field, raw, control))
    },
    [applyField, clipId, projectSettingId, trackEffectId, trackId],
  )

  const renderControl = (field: string, control: ControlSpec) => {
    const raw = params[field]
    const kind = control.kind

    if (kind === 'hidden') return null

    if (kind === 'color_stop_list') {
      const minItems = typeof control.min_items === 'number' ? control.min_items : 0
      const maxItems = typeof control.max_items === 'number' ? control.max_items : undefined
      return (
        <ParamColorStopList
          value={raw}
          minItems={minItems}
          maxItems={maxItems}
          jobTheme={jobTheme}
          onCommit={(stops) => setField(field, stops, control, true)}
        />
      )
    }

    if (kind === 'color_list') {
      const minItems = typeof control.min_items === 'number' ? control.min_items : 0
      const maxItems = typeof control.max_items === 'number' ? control.max_items : undefined
      return (
        <ParamColorList
          value={raw}
          minItems={minItems}
          maxItems={maxItems}
          jobTheme={jobTheme}
          onCommit={(swatches) => setField(field, swatches, control, true)}
        />
      )
    }

    if (kind === 'unknown') {
      return <ParamUnknown label={field} value={raw} />
    }

    if (kind === 'file') {
      const accept = Array.isArray(control.accept)
        ? control.accept.filter((x): x is string => typeof x === 'string')
        : []
      const uploadKind =
        typeof control.upload_kind === 'string' ? control.upload_kind : 'default'
      const maxBytes =
        typeof control.max_bytes === 'number'
          ? control.max_bytes
          : uploadMaxBytes(uploadKind, serverConfig)
      return (
        <ParamFile
          value={typeof raw === 'string' ? raw : String(raw ?? '')}
          fieldName={field}
          uploadKind={uploadKind}
          uploadContext={{
            clip_type: detail.clip_type,
            plugin_id: detail.plugin_id,
          }}
          accept={accept}
          maxBytes={maxBytes}
          nullable={Boolean(control.nullable)}
          stockBrowse={Boolean(control.stock_browse) && Boolean(pexelsAvailable)}
          onOpenStockBrowse={() => openStockBrowse(field, control)}
          onCommit={(v) => setField(field, v, control, true)}
        />
      )
    }

    if (kind === 'text') {
      const readOnly = Boolean(control.read_only)
      return (
        <ParamText
          value={typeof raw === 'string' ? raw : String(raw ?? '')}
          readOnly={readOnly}
          onCommit={(v) => setField(field, v, control, true)}
        />
      )
    }

    if (kind === 'textarea') {
      const rows = typeof control.rows === 'number' ? control.rows : 4
      const readOnly = Boolean(control.read_only)
      return (
        <ParamText
          multiline
          rows={rows}
          value={typeof raw === 'string' ? raw : String(raw ?? '')}
          readOnly={readOnly}
          onCommit={(v) => setField(field, v, control, true)}
        />
      )
    }

    if (kind === 'number') {
      const step = typeof control.step === 'number' ? control.step : 0.1
      return (
        <ParamNumber
          value={typeof raw === 'number' ? raw : Number(raw ?? 0)}
          step={step}
          onCommit={(v) => setField(field, v, control, true)}
        />
      )
    }

    if (kind === 'slider') {
      const mn = typeof control.minimum === 'number' ? control.minimum : 0
      const mx = typeof control.maximum === 'number' ? control.maximum : 1
      const step = typeof control.step === 'number' ? control.step : 0.1
      const showAs = typeof control.show_as === 'string' ? control.show_as : undefined
      const numericValue = typeof raw === 'number' ? raw : Number(raw ?? mn)
      if (showAs === 'anchor') {
        const axis = control.axis === 'x' ? 'x' : 'y'
        return (
          <ParamAnchorSlider
            value={numericValue}
            axis={axis}
            step={step}
            onCommit={(v) => setField(field, v, control, true)}
          />
        )
      }
      if (showAs === 'rotation') {
        const presets = Array.isArray(control.presets)
          ? control.presets.filter((p): p is number => typeof p === 'number')
          : undefined
        return (
          <ParamRotationSlider
            value={numericValue}
            minimum={mn}
            maximum={mx}
            step={step}
            presets={presets}
            onCommit={(v) => setField(field, v, control, true)}
          />
        )
      }
      return (
        <ParamSlider
          value={numericValue}
          minimum={mn}
          maximum={mx}
          step={step}
          showAs={showAs}
          onCommit={(v) => setField(field, v, control, true)}
        />
      )
    }

    if (kind === 'toggle') {
      return (
        <ParamToggle
          value={Boolean(raw)}
          onChange={(v) => setField(field, v, control)}
        />
      )
    }

    if (kind === 'select' || kind === 'typography_role') {
      const opts = Array.isArray(control.options) ? control.options.map(String) : []
      if (isTypographyRoleControl(field, control)) {
        const current =
          typeof raw === 'string'
            ? raw
            : typeof params.role === 'string'
              ? params.role
              : String(opts[0] ?? 'body_medium')
        return (
          <ParamTypographyRole
            value={current}
            options={opts}
            onChange={(v) => setField(field, v, control)}
          />
        )
      }
      const optionLabels = detail.labels.fields[field]?.options
      return (
        <ParamSelect
          value={raw == null ? null : String(raw)}
          options={opts}
          optionLabels={optionLabels}
          nullable={Boolean(control.nullable)}
          onChange={(v) => setField(field, v, control)}
        />
      )
    }

    if (kind === 'segmented_enum') {
      const opts = Array.isArray(control.options) ? control.options.map(String) : []
      const optionLabels = detail.labels.fields[field]?.options
      return (
        <ParamSegmentedEnum
          value={String(raw ?? opts[0] ?? '')}
          options={opts}
          optionLabels={optionLabels}
          onChange={(v) => setField(field, v, control)}
        />
      )
    }

    if (kind === 'theme_or_color') {
      return (
        <ParamThemeOrColor
          value={raw == null ? null : String(raw)}
          nullable={Boolean(control.nullable)}
          jobTheme={jobTheme}
          onChange={(v) => setField(field, v, control)}
        />
      )
    }

    if (kind === 'camera_orbit') {
      const azimuth = typeof raw === 'number' ? raw : 0
      const elevField = orbitElevationField(field)
      const elevation = typeof params[elevField] === 'number' ? params[elevField] : 0
      const elControl: ControlSpec = (controls[elevField] as ControlSpec | undefined) ?? { kind: 'hidden' }
      return (
        <ParamCameraOrbit
          variant={orbitVariant(control, field)}
          azimuth={azimuth}
          elevation={elevation}
          onCommit={(az, el) => {
            setField(field, az, control, true)
            setField(elevField, el, elControl, true)
          }}
        />
      )
    }

    if (kind === 'bus_select') {
      return (
        <ParamSelect
          value={raw == null ? null : String(raw)}
          options={busNames}
          nullable
          onChange={(v) => setField(field, v, control)}
        />
      )
    }

    return <ParamUnknown label={field} value={raw} />
  }

  return (
    <div className="flex flex-col gap-3">
      {sections.map((sec) => {
        if (!sec || typeof sec !== 'object') return null
        const id = (sec as { id?: string }).id
        if (id === TIMING_SECTION_ID) return null
        const fields = (sec as { fields?: unknown }).fields
        if (!Array.isArray(fields)) return null
        const title =
          (id && detail.labels.sections[id]) ||
          (typeof (sec as { title_key?: string }).title_key === 'string'
            ? (sec as { title_key: string }).title_key
            : id ?? 'Section')

        return (
          <div key={String(id)} className="flex flex-col gap-2">
            <h3 className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
              {title}
            </h3>
            {fields.map((field) => {
              if (typeof field !== 'string') return null
              const control = controls[field]
              if (!control || control.kind === 'hidden') return null
              if (isStockAttributionControl(field, control)) {
                const attribution = params[field]
                if (typeof attribution !== 'string' || !attribution.trim()) return null
              }
              const meta = detail.labels.fields[field]
              const label = meta?.label ?? field
              const invalid = invalidFields.has(field)
              return (
                <div
                  key={field}
                  className={
                    invalid ? 'rounded-md ring-1 ring-inset ring-yellow-500/60' : undefined
                  }
                >
                  <ParamField
                    label={label}
                    description={meta?.description}
                  >
                    {renderControl(field, control)}
                  </ParamField>
                </div>
              )
            })}
          </div>
        )
      })}
    </div>
  )
}
