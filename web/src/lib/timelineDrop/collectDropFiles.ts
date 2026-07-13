/** Collect all files from a drag-and-drop, including folder contents. */

function entryFromDataTransferItem(item: DataTransferItem): FileSystemEntry | null {
  if (item.kind !== 'file') return null
  return item.webkitGetAsEntry?.() ?? null
}

function readFileEntry(entry: FileSystemFileEntry): Promise<File> {
  return new Promise((resolve, reject) => {
    entry.file(resolve, reject)
  })
}

async function readDirectoryEntry(entry: FileSystemDirectoryEntry): Promise<File[]> {
  const reader = entry.createReader()
  const collected: File[] = []

  for (;;) {
    const batch = await new Promise<FileSystemEntry[]>((resolve, reject) => {
      reader.readEntries(resolve, reject)
    })
    if (batch.length === 0) break
    for (const child of batch) {
      collected.push(...(await readEntry(child)))
    }
  }

  return collected
}

async function readEntry(entry: FileSystemEntry): Promise<File[]> {
  if (entry.isFile) {
    return [await readFileEntry(entry as FileSystemFileEntry)]
  }
  if (entry.isDirectory) {
    return readDirectoryEntry(entry as FileSystemDirectoryEntry)
  }
  return []
}

/** Stable import order — numeric prefixes sort naturally (Suno-style exports). */
export function sortDropFilesByName(files: File[]): File[] {
  return [...files].sort((a, b) =>
    a.name.localeCompare(b.name, undefined, { numeric: true, sensitivity: 'base' }),
  )
}

/**
 * Expand folder drops via the File System Access entry API. For loose
 * multi-file drags, ``DataTransfer.files`` is more reliable — on some
 * platforms ``items`` only exposes one entry even when many files are selected.
 */
export async function collectDropFiles(dataTransfer: DataTransfer): Promise<File[]> {
  const flatFiles = [...dataTransfer.files]
  const items = dataTransfer.items

  if (!items || items.length === 0) {
    return sortDropFilesByName(flatFiles)
  }

  const fromEntries: File[] = []
  let hasDirectory = false

  for (let i = 0; i < items.length; i++) {
    const entry = entryFromDataTransferItem(items[i]!)
    if (!entry) continue
    if (entry.isDirectory) {
      hasDirectory = true
      fromEntries.push(...(await readEntry(entry)))
    } else if (entry.isFile) {
      fromEntries.push(...(await readEntry(entry)))
    }
  }

  if (hasDirectory) {
    return sortDropFilesByName(fromEntries)
  }

  if (flatFiles.length > 0) {
    return sortDropFilesByName(flatFiles)
  }

  return sortDropFilesByName(fromEntries)
}
