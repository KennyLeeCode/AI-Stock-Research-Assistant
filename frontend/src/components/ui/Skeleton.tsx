import styles from './Skeleton.module.css'

type SkeletonVariant = 'text' | 'heading' | 'block' | 'circle'

interface SkeletonProps {
  variant?: SkeletonVariant
  /** CSS width, e.g. `'60%'` or `120`. Defaults to full width. */
  width?: string | number
  /** CSS height. Required for `block` and `circle`. */
  height?: string | number
  className?: string
}

/**
 * A single shimmering placeholder.
 *
 * Skeletons rather than spinners: a skeleton preserves the final layout, so
 * content does not jump when it arrives, and it communicates *what* is loading
 * rather than merely that something is.
 *
 * Marked `aria-hidden` - the loading state is announced once by the containing
 * region's `aria-busy`, not repeated by every placeholder bar.
 */
export function Skeleton({
  variant = 'text',
  width,
  height,
  className,
}: SkeletonProps) {
  const classes = [styles.skeleton, styles[variant], className]
    .filter(Boolean)
    .join(' ')

  return (
    <span
      className={classes}
      style={{ width, height }}
      aria-hidden="true"
    />
  )
}

interface SkeletonTextProps {
  /** Number of lines to render. */
  lines?: number
  className?: string
}

/**
 * A paragraph-shaped group of skeleton lines.
 *
 * The last line is rendered short, which is what real wrapped text looks like
 * and what stops the placeholder reading as a solid block.
 */
export function SkeletonText({ lines = 3, className }: SkeletonTextProps) {
  return (
    <div className={`${styles.group} ${className ?? ''}`}>
      {Array.from({ length: lines }, (_, index) => (
        <Skeleton
          key={index}
          variant="text"
          width={index === lines - 1 ? '65%' : '100%'}
        />
      ))}
    </div>
  )
}
