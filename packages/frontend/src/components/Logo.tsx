/** GridSense's mark: a white lightning bolt, on the navbar's blue square. */
export function Logo({ size = 24 }: { size?: number }) {
    return (
        <svg width={size} height={size} viewBox='0 0 24 24' fill='none' aria-hidden='true'>
            <path d='M13.5 2.5 6.5 13h5l-1 8.5 7-10.5h-5l1-8.5Z' fill='white' stroke='white' strokeWidth='1' strokeLinejoin='round' />
        </svg>
    )
}
