declare module '@tarojs/components' {
  import { ComponentType, HTMLAttributes, ReactNode } from 'react'

  interface ViewProps extends HTMLAttributes<HTMLElement> {
    onClick?: (event: any) => void
    className?: string
    style?: React.CSSProperties | string
  }

  interface TextProps extends HTMLAttributes<HTMLElement> {
    className?: string
    style?: React.CSSProperties | string
  }

  interface ImageProps extends HTMLAttributes<HTMLElement> {
    src: string
    className?: string
    style?: React.CSSProperties | string
    mode?: string
    lazyLoad?: boolean
  }

  interface ScrollViewProps extends ViewProps {
    scrollY?: boolean
    scrollX?: boolean
    onScrollToLower?: () => void
    onScrollToUpper?: () => void
    className?: string
    style?: React.CSSProperties | string
    showScrollbar?: boolean
  }

  interface InputProps extends HTMLAttributes<HTMLElement> {
    value?: string
    placeholder?: string
    type?: string
    className?: string
    style?: React.CSSProperties | string
    onInput?: (e: any) => void
    onFocus?: (e: any) => void
    onBlur?: (e: any) => void
    onConfirm?: () => void
  }

  interface ButtonProps extends HTMLAttributes<HTMLElement> {
    type?: string
    className?: string
    style?: React.CSSProperties | string
    onClick?: (event: any) => void
    openType?: string
  }

  interface NavigatorProps extends HTMLAttributes<HTMLElement> {
    url: string
    className?: string
    openType?: string
  }

  interface FormProps extends HTMLAttributes<HTMLElement> {
    onSubmit?: (e: any) => void
    className?: string
  }

  interface SwiperProps extends ViewProps {
    indicatorDots?: boolean
    autoplay?: boolean
    interval?: number
    duration?: number
    circular?: boolean
    className?: string
  }

  interface SwiperItemProps extends ViewProps {
    className?: string
  }

  interface IconProps extends HTMLAttributes<HTMLElement> {
    type?: string
    size?: string | number
    color?: string
  }

  interface LabelProps extends HTMLAttributes<HTMLElement> {
    for?: string
    className?: string
  }

  interface PickerProps extends ViewProps {
    mode?: string
    range?: any[]
    value?: number | number[]
    onChange?: (e: any) => void
    className?: string
  }

  interface CheckboxGroupProps extends ViewProps {
    onChange?: (e: any) => void
    className?: string
  }

  interface CheckboxProps extends ViewProps {
    value?: string
    checked?: boolean
    className?: string
    color?: string
  }

  interface RadioGroupProps extends ViewProps {
    onChange?: (e: any) => void
    className?: string
  }

  interface RadioProps extends ViewProps {
    value?: string
    checked?: boolean
    className?: string
    color?: string
  }

  interface TextareaProps extends HTMLAttributes<HTMLElement> {
    value?: string
    placeholder?: string
    maxlength?: number
    className?: string
    style?: React.CSSProperties | string
    onInput?: (e: any) => void
  }

  interface BlockProps {
    children?: ReactNode
  }

  interface MovableAreaProps extends ViewProps {}
  interface MovableViewProps extends ViewProps {}

  export const View: ComponentType<ViewProps>
  export const Text: ComponentType<TextProps>
  export const Image: ComponentType<ImageProps>
  export const ScrollView: ComponentType<ScrollViewProps>
  export const Input: ComponentType<InputProps>
  export const Button: ComponentType<ButtonProps>
  export const Navigator: ComponentType<NavigatorProps>
  export const Form: ComponentType<FormProps>
  export const Swiper: ComponentType<SwiperProps>
  export const SwiperItem: ComponentType<SwiperItemProps>
  export const Icon: ComponentType<IconProps>
  export const Label: ComponentType<LabelProps>
  export const Picker: ComponentType<PickerProps>
  export const CheckboxGroup: ComponentType<CheckboxGroupProps>
  export const Checkbox: ComponentType<CheckboxProps>
  export const RadioGroup: ComponentType<RadioGroupProps>
  export const Radio: ComponentType<RadioProps>
  export const Textarea: ComponentType<TextareaProps>
  export const Block: ComponentType<BlockProps>
  export const MovableArea: ComponentType<MovableAreaProps>
  export const MovableView: ComponentType<MovableViewProps>
}
