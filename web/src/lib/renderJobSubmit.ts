import { createJob, isJobActive, listJobs } from '@/lib/jobsClient'
import { previewDimensionsFromMeta } from '@/lib/previewDimensions'
import { toGraphJSON, useProjectStore } from '@/store/projectStore'

type RenderSubmitMode = 'full' | 'preview'

export async function submitCurrentProjectRender(mode: RenderSubmitMode = 'full'): Promise<string> {
  const state = useProjectStore.getState()
  const graph = toGraphJSON(state)
  const previewSize =
    mode === 'preview'
      ? previewDimensionsFromMeta({ width: state.meta.width, height: state.meta.height })
      : null
  const payload = {
    ...graph,
    ...(previewSize ? { width: previewSize.width, height: previewSize.height } : {}),
    parallelism: state.appSettings.renderParallelism,
    video_encoder: state.appSettings.videoEncoder,
  }
  const { job_id } = await createJob(payload as unknown as Record<string, unknown>)
  return job_id
}

export async function projectHasActiveRenderJobs(): Promise<boolean> {
  const jobs = await listJobs()
  return jobs.some((job) => isJobActive(job.status))
}
