import { Icon } from '@blueprintjs/core'

export interface Step<K extends string> {
    key:   K
    title: string
}

interface StepsProps<K extends string> {
    steps:     Step<K>[]
    current:   K
    canReach:  (key: K) => boolean       // a step one can jump to: done, or any of them when editing
    onSelect:  (key: K) => void
}

/** A wizard's steps in a row: done ones ticked, the current one blue, the rest grey; reachable ones clickable. */
export function Steps<K extends string>({ steps, current, canReach, onSelect }: StepsProps<K>) {
    const currentIndex = steps.findIndex(step => step.key === current)

    return (
        <div className='flex items-center gap-2'>
            {steps.map((step, index) => {
                const isCurrent = index === currentIndex
                const isDone = index < currentIndex
                const isReachable = !isCurrent && canReach(step.key)

                let circle = 'border-gray-300 text-gray-400'
                let label = 'text-gray-400'

                if (isDone) {
                    circle = 'border-blue-600 bg-blue-600 text-white'
                    label = 'text-gray-700'
                }

                if (isCurrent) {
                    circle = 'border-blue-600 text-blue-600'
                    label = 'font-semibold text-gray-900'
                }

                return (
                    <div key={step.key} className={`flex items-center gap-2 ${index < steps.length - 1 ? 'flex-1' : ''}`}>
                        <div
                            role='button'
                            tabIndex={isReachable ? 0 : -1}
                            aria-current={isCurrent ? 'step' : undefined}
                            onClick={() => isReachable && onSelect(step.key)}
                            className={`flex shrink-0 items-center gap-2 ${isReachable ? 'cursor-pointer' : 'cursor-default'}`}
                        >
                            <span className={`flex h-6 w-6 items-center justify-center rounded-full border-2 text-xs font-semibold ${circle}`}>
                                {isDone ? <Icon icon='tick' size={12} /> : index + 1}
                            </span>
                            <span className={`text-sm whitespace-nowrap ${label}`}>{step.title}</span>
                        </div>

                        {index < steps.length - 1 && (
                            <div className={`h-px min-w-4 flex-1 ${isDone ? 'bg-blue-600' : 'bg-gray-300'}`} />
                        )}
                    </div>
                )
            })}
        </div>
    )
}
