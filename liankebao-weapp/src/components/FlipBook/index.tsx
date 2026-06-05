import { Component } from 'react'
import { View } from '@tarojs/components'
import FlipPage from './FlipPage'
import './FlipBook.scss'

interface FlipBookProps {
  pages: Array<{
    type: 'cover' | 'contact' | 'products' | 'qrcode' | 'company'
    data: any
  }>
  currentPage?: number
  onPageChange?: (page: number) => void
}

interface FlipBookState {
  currentPage: number
  touchStartX: number
  animating: boolean
}

export default class FlipBook extends Component<FlipBookProps, FlipBookState> {
  state: FlipBookState = {
    currentPage: this.props.currentPage || 0,
    touchStartX: 0,
    animating: false,
  }

  handleTouchStart = (e: any) => {
    this.setState({ touchStartX: e.touches[0].clientX })
  }

  handleTouchEnd = (e: any) => {
    const { currentPage, touchStartX } = this.state
    const { pages } = this.props
    const diffX = e.changedTouches[0].clientX - touchStartX

    if (Math.abs(diffX) > 50) {
      if (diffX < 0 && currentPage < pages.length - 1) {
        // 左滑：下一页
        this.setState({ animating: true })
        const next = currentPage + 1
        this.setState({ currentPage: next }, () => {
          setTimeout(() => this.setState({ animating: false }), 300)
          if (this.props.onPageChange) this.props.onPageChange(next)
        })
      } else if (diffX > 0 && currentPage > 0) {
        // 右滑：上一页
        this.setState({ animating: true })
        const prev = currentPage - 1
        this.setState({ currentPage: prev }, () => {
          setTimeout(() => this.setState({ animating: false }), 300)
          if (this.props.onPageChange) this.props.onPageChange(prev)
        })
      }
    }
  }

  goToPage = (page: number) => {
    const { pages } = this.props
    if (page < 0 || page >= pages.length) return
    this.setState({ currentPage: page, animating: true })
    setTimeout(() => this.setState({ animating: false }), 300)
    if (this.props.onPageChange) this.props.onPageChange(page)
  }

  render() {
    const { pages } = this.props
    const { currentPage } = this.state

    return (
      <View
        className='flipbook'
        onTouchStart={this.handleTouchStart}
        onTouchEnd={this.handleTouchEnd}
      >
        {pages.map((page, index) => (
          <FlipPage
            key={index}
            type={page.type}
            data={page.data}
            isActive={index === currentPage}
            position={
              index < currentPage ? 'prev' : index > currentPage ? 'next' : 'active'
            }
          />
        ))}
      </View>
    )
  }
}
