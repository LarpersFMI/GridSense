import { Button, Card, Icon } from '@blueprintjs/core'
import type { Dataset, Trigger } from '@gridsense/shared/domain'
import { formatCondition, formatGrouping } from './format'
import { TRIGGER_TEMPLATES, createFromTemplate } from './templates'

interface TemplatePickerProps {
    dataset:  Dataset.Triggerable
    onPick:   (draft: Trigger) => void
    onCancel: () => void
}

/** How a new trigger starts: blank, or from one of the templates on this dataset — then edited before it's saved. */
export function TemplatePicker({ dataset, onPick, onCancel }: TemplatePickerProps) {
    const templates = TRIGGER_TEMPLATES.filter(template => template.dataset === dataset)

    return (
        <div className='flex flex-col gap-3'>
            <div className='flex items-center justify-between'>
                <h4 className='bp6-heading m-0'>New trigger on {dataset}</h4>
                <Button icon='cross' variant='minimal' text='Cancel' onClick={onCancel} />
            </div>

            <Card compact interactive onClick={() => onPick(createFromTemplate(dataset, null))}>
                <div className='flex items-center gap-3'>
                    <Icon icon='plus' className='text-gray-500' />
                    <div>
                        <div className='font-semibold'>Blank</div>
                        <div className='text-xs text-gray-500'>No conditions yet: write them from the columns.</div>
                    </div>
                </div>
            </Card>

            {templates.length > 0 && <div className='text-xs font-semibold tracking-wide text-gray-500 uppercase'>Templates</div>}

            {templates.map(template => (
                <Card key={template.key} compact interactive onClick={() => onPick(createFromTemplate(dataset, template))}>
                    <div className='flex items-start gap-3'>
                        <Icon icon={template.icon} intent='primary' className='mt-0.5' />
                        <div className='flex min-w-0 flex-col gap-1'>
                            <div className='font-semibold'>{template.trigger.name}</div>
                            <div className='text-xs text-gray-500'>{template.trigger.description}</div>
                            <div className='font-mono text-xs'>
                                {template.trigger.conditions.map((condition, index) => (
                                    <div key={index}>{formatCondition(condition)}</div>
                                ))}
                            </div>
                            <div className='text-xs text-gray-500'>{formatGrouping(template.trigger.grouping)}</div>
                        </div>
                    </div>
                </Card>
            ))}
        </div>
    )
}
