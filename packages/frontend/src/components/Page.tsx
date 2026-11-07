import type { ReactNode } from 'react'

/** A centered page of content (triggers, activity); the dataset viewer fills the screen instead. */
export function Page({ children }: { children: ReactNode }) {
    return (
        <div className='mx-auto max-w-6xl p-6'>
            {children}
        </div>
    )
}
