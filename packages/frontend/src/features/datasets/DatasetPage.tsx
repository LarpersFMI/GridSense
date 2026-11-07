import { useState } from 'react'
import { Button } from '@blueprintjs/core'
import { useNavigate } from '@tanstack/react-router'
import { Dataset } from '@gridsense/shared/domain'
import { Dropdown } from '@/components/Dropdown'
import { DatasetSDK } from '@/SDKs/DatasetSDK/sdk'
import { DatasetPreview } from '@/SDKs/DatasetSDK/ui/DatasetPreview'
import { formatCount } from '@/utils/format'
import { ChartsPanel } from './charts/ChartsPanel'
import { DatasetSidebar } from './DatasetSidebar'

interface DatasetPageProps {
    name: Dataset.Name
}

/** The dataset viewer: its latest rows on the left, the triggers that read it and the pipelines that write it on the right. */
export function DatasetPage({ name }: DatasetPageProps) {
    const navigate = useNavigate()
    const [orderBy, setOrderBy] = useState<string | null>(null)

    const [, [previewRequest]] = DatasetSDK.useWith(
        () => null,
        query => [query.preview(name, orderBy)],
    )

    const preview = previewRequest.data

    function handleDatasetChange(next: Dataset.Name) {
        void navigate({ to: '/datasets/$name', params: { name: next } })
    }

    return (
        <div className='flex h-full min-h-0'>
            <section className='flex min-w-0 flex-1 flex-col'>
                <div className='flex items-center gap-3 border-b border-gray-200 bg-white px-4 py-2'>
                    <Dropdown
                        value={name}
                        options={Dataset.Name.options.map(option => ({ value: option, label: option }))}
                        onChange={handleDatasetChange}
                    />

                    {preview && (
                        <>
                            <span className='text-xs text-gray-500'>
                                Latest {formatCount(preview.rows.length)} of {formatCount(preview.total)} rows
                                · {preview.columns.length} columns · newest by
                            </span>
                            <Dropdown
                                value={preview.orderBy}
                                options={timestampColumns(preview).map(column => ({ value: column, label: column }))}
                                onChange={setOrderBy}
                            />
                        </>
                    )}

                    <div className='ml-auto'>
                        <Button
                            icon='refresh'
                            variant='minimal'
                            text='Refresh'
                            loading={previewRequest.isFetching}
                            onClick={() => void previewRequest.refetch()}
                        />
                    </div>
                </div>

                {/* Blueprint's table scrolls itself, and fills this box. */}
                <div className='min-h-0 flex-1'>
                    <DatasetPreview name={name} orderBy={orderBy} onOrderBy={setOrderBy} />
                </div>

                {preview && <ChartsPanel key={name} dataset={name} columns={preview.columns} />}
            </section>

            <aside className='w-[600px] shrink-0 overflow-auto border-l border-gray-200 bg-white'>
                <DatasetSidebar dataset={name} />
            </aside>
        </div>
    )
}

function timestampColumns(preview: Dataset.Preview): string[] {
    return preview.columns
        .filter(column => column.type === 'timestamp')
        .map(column => column.name)
}
