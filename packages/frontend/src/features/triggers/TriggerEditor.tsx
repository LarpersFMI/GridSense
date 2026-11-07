import { Button, FormGroup, InputGroup, NumericInput, Section, SectionCard, Switch, TextArea } from '@blueprintjs/core'
import { zodResolver } from '@hookform/resolvers/zod'
import { useNavigate } from '@tanstack/react-router'
import { Controller, useFieldArray, useForm, type FieldErrors } from 'react-hook-form'
import type { z } from 'zod'
import { Dataset, Trigger } from '@gridsense/shared/domain'
import { Choice, type ChoiceOption } from '@/components/Choice'
import { Dropdown, type DropdownOption } from '@/components/Dropdown'
import { DatasetSDK } from '@/SDKs/DatasetSDK/sdk'
import { TriggerSDK } from '@/SDKs/TriggerSDK/sdk'
import { ConditionRow } from './ConditionRow'
import { DEFAULT_CRON, INCREMENTAL_COLUMNS } from './draft'

type TriggerInput = z.input<typeof Trigger.Schema>

const ON_OPTIONS: ChoiceOption<Trigger.On['type']>[] = [
    { value: 'dataset', label: 'When a dataset updates', icon: 'database' },
    { value: 'schedule', label: 'On a schedule', icon: 'time' },
]

// Datasets will be added: a dropdown, not tabs.
const DATASET_OPTIONS: DropdownOption<Dataset.Name>[] = Dataset.Name.options.map(name => ({ value: name, label: name }))

const MATCH_OPTIONS: ChoiceOption<Trigger.Condition.Match>[] = [
    { value: 'all', label: 'All hold' },
    { value: 'any', label: 'Any holds' },
]

// Too long for tabs: a dropdown.
const GROUPING_OPTIONS: DropdownOption<Trigger.Grouping['type']>[] = [
    { value: 'window', label: 'one hit per window of consecutive hours' },
    { value: 'hour', label: 'one hit per hour' },
    { value: 'run', label: 'one hit per check' },
]

interface TriggerEditorProps {
    trigger: Trigger
    isNew:   boolean
    onDone?: () => void          // saved, deleted or cancelled; without it, the editor goes back to /triggers
}

/**
 * A trigger, whole: what it watches, its conditions on the datasets' columns (read from the files), how matching
 * hours become hits. Validated with `Trigger.Schema`, the server's own.
 */
export function TriggerEditor({ trigger, isNew, onDone }: TriggerEditorProps) {
    const navigate = useNavigate()

    const form = useForm<TriggerInput, unknown, Trigger>({
        resolver:      zodResolver(Trigger.Schema),
        defaultValues: trigger,
    })

    const conditions = useFieldArray({
        control: form.control,
        name:    'conditions',
    })

    const on = form.watch('on')
    const grouping = form.watch('grouping')
    const errors = form.formState.errors

    const [, [predictionsRequest, pricesRequest]] = DatasetSDK.useWith(
        () => null,
        query => [query.describe('predictions'), query.describe('prices')],
    )

    const descriptions: Partial<Record<Dataset.Name, Dataset.Description>> = {
        predictions: predictionsRequest.data,
        prices:      pricesRequest.data,
    }

    async function finish() {
        if (onDone)
            onDone()
        else
            await navigate({ to: '/triggers' })
    }

    async function handleSave(values: Trigger) {
        try {
            if (isNew)
                await TriggerSDK.actions.trigger.create(values)
            else
                await TriggerSDK.actions.trigger.update(values)
        }
        catch {
            // The action reported it; the editor stays open with what was written.
            return
        }

        await finish()
    }

    async function handleDelete() {
        try {
            await TriggerSDK.actions.trigger.remove(trigger.id)
        }
        catch {
            return
        }

        await finish()
    }

    function handleOnTypeChange(type: Trigger.On['type']) {
        if (type === 'schedule') {
            form.setValue('on', { type: 'schedule', cron: DEFAULT_CRON })
            form.setValue('conditions', [])
            form.setValue('grouping', { type: 'run' })
        }
        else {
            handleDatasetChange('predictions')
        }
    }

    function handleDatasetChange(dataset: Dataset.Name) {
        form.setValue('on', {
            type:              'dataset',
            dataset,
            incrementalColumn: INCREMENTAL_COLUMNS[dataset],
        })
    }

    function handleGroupingChange(type: Trigger.Grouping['type']) {
        if (type === 'window')
            form.setValue('grouping', { type: 'window', minHours: 2, maxHours: 6 })
        else
            form.setValue('grouping', { type })
    }

    function handleAddCondition() {
        conditions.append({
            dataset:  on.type === 'dataset' ? on.dataset : 'predictions',
            column:   '',
            operator: '>=',
            value:    0,
        })
    }

    return (
        // Blueprint's `form { display: block }` beats Tailwind's `flex` on the form itself: the layout is the div's.
        <form onSubmit={form.handleSubmit(handleSave)}>
            <div className='flex flex-col gap-4'>
                <div className='flex items-center justify-between'>
                    <h2 className='bp6-heading m-0'>{isNew ? 'New trigger' : trigger.name}</h2>
                    <div className='flex gap-2'>
                        {!isNew && (
                            <Button intent='danger' variant='minimal' icon='trash' text='Delete' onClick={handleDelete} />
                        )}
                        <Button text='Cancel' onClick={() => void finish()} />
                        <Button
                            type='submit'
                            intent='primary'
                            icon='floppy-disk'
                            text='Save'
                            loading={form.formState.isSubmitting}
                        />
                    </div>
                </div>

                <Section title='Trigger' icon='antenna' compact>
                    <SectionCard>
                        <FormGroup label='Name' intent={errors.name ? 'danger' : 'none'} helperText={errors.name?.message}>
                            <Controller
                                control={form.control}
                                name='name'
                                render={({ field }) => (
                                    <InputGroup
                                        value={field.value}
                                        onValueChange={field.onChange}
                                        onBlur={field.onBlur}
                                        placeholder='Zero-cost window'
                                    />
                                )}
                            />
                        </FormGroup>
                        <FormGroup label='Description' helperText='Tells the agent what you meant.'>
                            <Controller
                                control={form.control}
                                name='description'
                                render={({ field }) => (
                                    <TextArea
                                        value={field.value}
                                        onChange={event => field.onChange(event.currentTarget.value)}
                                        onBlur={field.onBlur}
                                        fill
                                        rows={2}
                                    />
                                )}
                            />
                        </FormGroup>
                        <Controller
                            control={form.control}
                            name='enabled'
                            render={({ field }) => (
                                <Switch
                                    label='Enabled'
                                    checked={field.value}
                                    onChange={event => field.onChange(event.currentTarget.checked)}
                                />
                            )}
                        />
                    </SectionCard>
                </Section>

                <Section title="When it's checked" icon='automatic-updates' compact>
                    <SectionCard>
                        <div className='mb-4'>
                            <Choice id='trigger-on' value={on.type} options={ON_OPTIONS} onChange={handleOnTypeChange} />
                        </div>

                        {on.type === 'dataset' && (
                            <div className='field-rows'>
                                <FormGroup label='Dataset' inline>
                                    <Dropdown value={on.dataset} options={DATASET_OPTIONS} onChange={handleDatasetChange} />
                                </FormGroup>
                                <FormGroup
                                    label='New rows by'
                                    helperText='A timestamp column that grows as rows are appended: the trigger reads the rows past what it read last.'
                                    intent={errorOf(errors, 'on') ? 'danger' : 'none'}
                                    inline
                                >
                                    <IncrementalColumnSelect
                                        value={on.incrementalColumn}
                                        description={descriptions[on.dataset]}
                                        onChange={column => form.setValue('on', { ...on, incrementalColumn: column })}
                                    />
                                </FormGroup>
                            </div>
                        )}

                        {on.type === 'schedule' && (
                            <div className='field-rows'>
                                <FormGroup
                                    label='Cron'
                                    helperText={errorOf(errors, 'on') ?? 'Five fields, Romanian time: 0 8 * * MON is Mondays at 08:00.'}
                                    intent={errorOf(errors, 'on') ? 'danger' : 'none'}
                                    inline
                                >
                                    <InputGroup
                                        value={on.cron}
                                        onValueChange={cron => form.setValue('on', { type: 'schedule', cron })}
                                        className='font-mono'
                                    />
                                </FormGroup>
                            </div>
                        )}
                    </SectionCard>
                </Section>

                {on.type === 'dataset' && (
                    <Section
                        title='Conditions'
                        icon='filter-list'
                        compact
                        rightElement={(
                            <Controller
                                control={form.control}
                                name='match'
                                render={({ field }) => (
                                    <Choice id='trigger-match' value={field.value} options={MATCH_OPTIONS} onChange={field.onChange} />
                                )}
                            />
                        )}
                    >
                        <SectionCard>
                            {conditions.fields.map((field, index) => (
                                <ConditionRow
                                    key={field.id}
                                    index={index}
                                    control={form.control}
                                    setValue={form.setValue}
                                    descriptions={descriptions}
                                    error={conditionError(errors, index)}
                                    onRemove={() => conditions.remove(index)}
                                />
                            ))}

                            {conditions.fields.length === 0 && (
                                <p className='text-gray-500'>No conditions: every new hour matches.</p>
                            )}

                            <Button icon='add' text='Add condition' variant='minimal' onClick={handleAddCondition} />
                        </SectionCard>
                    </Section>
                )}

                <Section title='Hits' icon='send-to' compact>
                    <SectionCard className='flex flex-wrap gap-4'>
                        <FormGroup label='Matching hours become'>
                            <Dropdown
                                value={grouping.type}
                                options={GROUPING_OPTIONS}
                                onChange={handleGroupingChange}
                            />
                        </FormGroup>

                        {grouping.type === 'window' && (
                            <>
                                <FormGroup label='Min hours'>
                                    <Controller
                                        control={form.control}
                                        name='grouping.minHours'
                                        render={({ field }) => (
                                            <div className='w-28'>
                                                <NumericInput value={field.value} onValueChange={field.onChange} min={1} fill />
                                            </div>
                                        )}
                                    />
                                </FormGroup>
                                <FormGroup
                                    label='Max hours'
                                    intent={errorOf(errors, 'grouping') ? 'danger' : 'none'}
                                    helperText={errorOf(errors, 'grouping')}
                                >
                                    <Controller
                                        control={form.control}
                                        name='grouping.maxHours'
                                        render={({ field }) => (
                                            <div className='w-28'>
                                                <NumericInput value={field.value} onValueChange={field.onChange} min={1} fill />
                                            </div>
                                        )}
                                    />
                                </FormGroup>
                            </>
                        )}

                        <FormGroup label='Cooldown (minutes)' helperText='The same window hits at most once per cooldown.'>
                            <Controller
                                control={form.control}
                                name='cooldownMinutes'
                                render={({ field }) => (
                                    <div className='w-36'>
                                        <NumericInput value={field.value} onValueChange={field.onChange} min={0} stepSize={60} majorStepSize={600} fill />
                                    </div>
                                )}
                            />
                        </FormGroup>
                    </SectionCard>
                </Section>
            </div>
        </form>
    )
}

interface IncrementalColumnSelectProps {
    value:       string
    description: Dataset.Description | undefined
    onChange:    (column: string) => void
}

/** The file's timestamp columns; before the file is described, only the current one. */
function IncrementalColumnSelect({ value, description, onChange }: IncrementalColumnSelectProps) {
    let columns = [value]

    if (description)
        columns = description.columns
            .filter(column => column.type === 'timestamp' && !column.computed)
            .map(column => column.name)

    return (
        <Dropdown
            value={value}
            options={columns.map(column => ({ value: column, label: column }))}
            onChange={onChange}
        />
    )
}

/** The first message zod gave anywhere under this field. */
function errorOf(errors: FieldErrors<TriggerInput>, field: 'on' | 'grouping'): string | undefined {
    const error = errors[field]

    if (!error)
        return undefined

    if (typeof error.message === 'string')
        return error.message

    for (const nested of Object.values(error))
        if (nested && typeof nested === 'object' && 'message' in nested && typeof nested.message === 'string')
            return nested.message

    return undefined
}

function conditionError(errors: FieldErrors<TriggerInput>, index: number): string | undefined {
    const error = errors.conditions?.[index]

    if (!error)
        return undefined

    if (typeof error.message === 'string')
        return error.message

    for (const field of ['column', 'operator', 'value'] as const) {
        const message = error[field]?.message

        if (typeof message === 'string')
            return `${field}: ${message}`
    }

    return undefined
}
