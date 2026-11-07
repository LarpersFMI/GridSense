import { useState } from 'react'
import { Tab, Tabs } from '@blueprintjs/core'
import { Dataset } from '@gridsense/shared/domain'
import { PipelineSDK } from '@/SDKs/PipelineSDK/sdk'
import { TriggerSDK } from '@/SDKs/TriggerSDK/sdk'
import { DatasetPipelines } from './DatasetPipelines'
import { DatasetTriggers } from './DatasetTriggers'

type Panel = 'triggers' | 'pipelines'

interface DatasetSidebarProps {
    dataset: Dataset.Name
}

/**
 * Everything around a dataset, beside its rows: the triggers that read it, and the pipelines that write it. A dataset
 * triggers aren't checked on (features: what the model read) has its pipelines only.
 */
export function DatasetSidebar({ dataset }: DatasetSidebarProps) {
    const triggerable = Dataset.Triggerable.safeParse(dataset).data ?? null
    const [panel, setPanel] = useState<Panel>(triggerable === null ? 'pipelines' : 'triggers')

    const triggers = TriggerSDK.useStore(TriggerSDK.selectors.list)

    // Loaded here too: the count shows before the tab is opened.
    const [pipelines] = PipelineSDK.useWith(
        PipelineSDK.selectors.list,
        query => [query.pipelines],
    )

    const triggerCount = triggers.filter(trigger => trigger.on.type === 'dataset' && trigger.on.dataset === dataset).length
    const writing = pipelines.filter(pipeline => pipeline.outputs.includes(dataset)).map(pipeline => pipeline.name)

    return (
        <div className='flex flex-col'>
            <div className='dataset-sidebar-tabs border-b border-gray-200 px-4'>
                <Tabs id='dataset-sidebar' selectedTabId={panel} onChange={next => setPanel(next as Panel)}>
                    <Tab
                        id='triggers'
                        icon='antenna'
                        title='Triggers'
                        tagContent={triggerCount}
                        tagProps={{ round: true }}
                        disabled={triggerable === null}
                    />
                    <Tab
                        id='pipelines'
                        icon='data-lineage'
                        title='Pipelines'
                        tagContent={writing.length}
                        tagProps={{ round: true }}
                    />
                </Tabs>
            </div>

            <div className='p-4'>
                {panel === 'triggers' && triggerable !== null && <DatasetTriggers dataset={triggerable} />}
                {panel === 'pipelines' && <DatasetPipelines dataset={dataset} />}
            </div>
        </div>
    )
}
