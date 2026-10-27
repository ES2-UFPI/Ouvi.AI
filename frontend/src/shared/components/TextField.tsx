import { type InputHTMLAttributes } from 'react'

interface TextFieldProps extends InputHTMLAttributes<HTMLInputElement> {
  label: string
  error?: string
}

export function TextField({ label, error, id, ...props }: TextFieldProps) {
  return (
    <div className="mb-5">
      <label htmlFor={id} className="block text-sm text-text-primary mb-1.5">
        {label}
      </label>
      <input
        id={id}
        className="w-full rounded-lg bg-bg-surface border border-border-subtle px-3.5 py-2.5 text-text-primary placeholder:text-text-muted outline-none focus:border-accent-en transition-colors"
        {...props}
      />
      {error && <p className="text-sm mt-1.5 text-accent-pt">{error}</p>}
    </div>
  )
}