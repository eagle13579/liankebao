import { Component } from 'react'
import { View, Text, Input, Textarea, Button, Image, ScrollView } from '@tarojs/components'
import Taro from '@tarojs/taro'
import NavBar from '../../components/NavBar'
import { brochureApi } from '../../api/digitalBrochure'
import './index.scss'

const STORAGE_KEY = 'card_editor_draft'

const STEP_LABELS = ['个人信息', '供需标签', '图片上传', '预览确认']

const PRESET_PROVIDE_TAGS = [
  '技术开发', '产品设计', '市场营销', '品牌策划',
  '投资融资', '供应链', '咨询服务', '培训教育',
  '软件开发', '硬件制造', '内容创作', '数据分析',
]

const PRESET_NEED_TAGS = [
  '找客户', '找渠道', '找合伙人', '找投资人',
  '招人才', '找供应商', '找技术', '找品牌合作',
  '找场地', '找流量', '找代理商', '找外包服务',
]

interface FormData {
  name: string
  company: string
  position: string
  bio: string
  provideTags: string[]
  needTags: string[]
  images: string[]
}

interface CardEditorState {
  step: number
  form: FormData
  submitting: boolean
  publishDone: boolean
  customProvideInput: string
  customNeedInput: string
}

export default class CardEditor extends Component<{}, CardEditorState> {
  state: CardEditorState = {
    step: 1,
    form: {
      name: '',
      company: '',
      position: '',
      bio: '',
      provideTags: [],
      needTags: [],
      images: [],
    },
    submitting: false,
    publishDone: false,
    customProvideInput: '',
    customNeedInput: '',
  }

  componentDidMount() {
    const params = Taro.getCurrentInstance()?.router?.params
    if (params?.editId) {
      this.loadExisting(params.editId as string)
    } else {
      this.loadDraft()
    }
  }

  // ===== 草稿持久化 =====

  loadDraft() {
    try {
      const saved = Taro.getStorageSync(STORAGE_KEY)
      if (saved) {
        this.setState({ form: saved })
        Taro.showToast({ title: '已恢复草稿', icon: 'none', duration: 1500 })
      }
    } catch {
      // ignore
    }
  }

  saveDraft() {
    const { form } = this.state
    Taro.setStorageSync(STORAGE_KEY, form)
    Taro.showToast({ title: '草稿已保存', icon: 'success' })
  }

  clearDraft() {
    Taro.removeStorageSync(STORAGE_KEY)
  }

  autoSaveDraft() {
    const { form } = this.state
    Taro.setStorageSync(STORAGE_KEY, form)
  }

  // ===== 编辑模式加载 =====

  loadExisting = async (id: string) => {
    try {
      const res: any = await brochureApi.getMine()
      if (res?.code === 200 && res.data) {
        const d = res.data
        this.setState({
          form: {
            name: d.name || '',
            company: d.company || '',
            position: d.position || '',
            bio: d.bio || '',
            provideTags: d.provide_tags || [],
            needTags: d.need_tags || [],
            images: d.images || [],
          },
        })
      }
    } catch {
      // start fresh
    }
  }

  // ===== Input handlers =====

  onInput = (e: any) => {
    const field = e.currentTarget.dataset.field as keyof FormData
    const value = e.detail?.value ?? ''
    this.setState((prev) => ({
      form: { ...prev.form, [field]: value },
    }))
  }

  toggleProvideTag = (tag: string) => {
    this.setState((prev) => {
      const tags = prev.form.provideTags.includes(tag)
        ? prev.form.provideTags.filter((t) => t !== tag)
        : [...prev.form.provideTags, tag]
      return { form: { ...prev.form, provideTags: tags } }
    })
  }

  toggleNeedTag = (tag: string) => {
    this.setState((prev) => {
      const tags = prev.form.needTags.includes(tag)
        ? prev.form.needTags.filter((t) => t !== tag)
        : [...prev.form.needTags, tag]
      return { form: { ...prev.form, needTags: tags } }
    })
  }

  addCustomProvideTag = () => {
    const tag = this.state.customProvideInput.trim()
    if (!tag) return
    if (this.state.form.provideTags.includes(tag)) {
      this.setState({ customProvideInput: '' })
      return
    }
    this.setState((prev) => ({
      form: { ...prev.form, provideTags: [...prev.form.provideTags, tag] },
      customProvideInput: '',
    }))
  }

  addCustomNeedTag = () => {
    const tag = this.state.customNeedInput.trim()
    if (!tag) return
    if (this.state.form.needTags.includes(tag)) {
      this.setState({ customNeedInput: '' })
      return
    }
    this.setState((prev) => ({
      form: { ...prev.form, needTags: [...prev.form.needTags, tag] },
      customNeedInput: '',
    }))
  }

  removeProvideTag = (tag: string) => {
    this.setState((prev) => ({
      form: { ...prev.form, provideTags: prev.form.provideTags.filter((t) => t !== tag) },
    }))
  }

  removeNeedTag = (tag: string) => {
    this.setState((prev) => ({
      form: { ...prev.form, needTags: prev.form.needTags.filter((t) => t !== tag) },
    }))
  }

  // ===== 图片上传 =====

  chooseImages = async () => {
    try {
      const remain = 9 - this.state.form.images.length
      if (remain <= 0) {
        Taro.showToast({ title: '最多上传9张图片', icon: 'none' })
        return
      }
      const res = await Taro.chooseMedia({ count: remain, mediaType: ['image'] })
      if (res.tempFiles?.length > 0) {
        const paths = res.tempFiles.map((f) => f.tempFilePath || f.path)
        this.setState((prev) => ({
          form: { ...prev.form, images: [...prev.form.images, ...paths] },
        }))
      }
    } catch {
      // cancelled or error
    }
  }

  removeImage = (index: number) => {
    this.setState((prev) => ({
      form: {
        ...prev.form,
        images: prev.form.images.filter((_, i) => i !== index),
      },
    }))
  }

  // ===== 步骤导航 =====

  nextStep = () => {
    const { step, form } = this.state
    if (step === 1) {
      if (!form.name.trim()) {
        Taro.showToast({ title: '请填写姓名', icon: 'none' })
        return
      }
    }
    this.setState((prev) => ({ step: Math.min(prev.step + 1, 4) }))
  }

  prevStep = () => {
    this.setState((prev) => ({ step: Math.max(prev.step - 1, 1) }))
  }

  goBack = () => {
    this.autoSaveDraft()
    Taro.navigateBack()
  }

  // ===== 发布 =====

  publish = async () => {
    this.setState({ submitting: true })
    try {
      const { form } = this.state
      const data = {
        name: form.name,
        company: form.company,
        position: form.position,
        bio: form.bio,
        provide_tags: form.provideTags,
        need_tags: form.needTags,
        images: form.images,
      }

      const res: any = await brochureApi.create(data)
      if (res?.code === 200) {
        const brochureId = res.data?.id
        if (brochureId) {
          await brochureApi.publish(brochureId)
        }
        this.clearDraft()
        this.setState({ publishDone: true })
        Taro.showToast({ title: '发布成功', icon: 'success' })
        setTimeout(() => {
          Taro.navigateTo({ url: `/pages/brochure-preview/index?id=${brochureId}` })
        }, 1200)
      } else {
        Taro.showToast({ title: res?.message || '发布失败', icon: 'error' })
      }
    } catch (e: any) {
      Taro.showToast({ title: e.message || '发布失败', icon: 'error' })
    } finally {
      this.setState({ submitting: false })
    }
  }

  // ===== 渲染: 步骤指示器 =====

  renderStepIndicator() {
    const { step } = this.state
    const dots = []
    for (let i = 1; i <= 4; i++) {
      dots.push(
        <View key={i} className={`step-dot ${step >= i ? 'active' : ''}`}>
          <Text className='dot-num'>{i}</Text>
        </View>
      )
      if (i < 4) {
        dots.push(<View key={`line-${i}`} className={`step-line ${step > i ? 'active' : ''}`} />)
      }
    }
    return (
      <View className='step-indicator'>
        <View className='dots-row'>{dots}</View>
        <Text className='step-label'>{STEP_LABELS[step - 1]} ({step}/4)</Text>
      </View>
    )
  }

  // ===== 渲染: Step1 个人信息 =====

  renderStep1() {
    const { form } = this.state
    return (
      <View className='step-content fade-in'>
        <View className='ai-hint'>
          <Text>📋 填写您的个人信息，用于展示在数字名片上</Text>
        </View>

        <View className='form-section glass'>
          <Text className='form-section-title'>基本信息</Text>
          <View className='form-group'>
            <Text className='form-label'>姓名 *</Text>
            <Input
              className='input-field'
              placeholder='请输入姓名'
              value={form.name}
              data-field='name'
              onInput={this.onInput}
            />
          </View>
          <View className='form-group'>
            <Text className='form-label'>公司 *</Text>
            <Input
              className='input-field'
              placeholder='请输入公司名称'
              value={form.company}
              data-field='company'
              onInput={this.onInput}
            />
          </View>
          <View className='form-group'>
            <Text className='form-label'>职位</Text>
            <Input
              className='input-field'
              placeholder='请输入职位，如 CEO / 创始人'
              value={form.position}
              data-field='position'
              onInput={this.onInput}
            />
          </View>
          <View className='form-group'>
            <Text className='form-label'>个人简介</Text>
            <Textarea
              className='input-field textarea'
              placeholder='简单介绍自己，突出专业领域和优势，最多200字'
              value={form.bio}
              data-field='bio'
              onInput={this.onInput}
              maxlength={200}
            />
            <Text className='char-count'>{form.bio.length}/200</Text>
          </View>
        </View>

        <View className='step-actions'>
          <Button className='btn-primary' onClick={this.nextStep}>
            下一步：供需标签 →
          </Button>
        </View>
      </View>
    )
  }

  // ===== 渲染: Step2 供需标签 =====

  renderStep2() {
    const { form, customProvideInput, customNeedInput } = this.state
    return (
      <View className='step-content fade-in'>
        <View className='ai-hint'>
          <Text>🏷️ 选择或自定义供需标签，AI将据此为您精准匹配合作伙伴</Text>
        </View>

        <View className='form-section glass'>
          <Text className='form-section-title'>我能提供 / 资源</Text>
          <View className='tags-grid'>
            {PRESET_PROVIDE_TAGS.map((tag) => (
              <View
                key={tag}
                className={`tag-chip ${form.provideTags.includes(tag) ? 'active provide' : ''}`}
                onClick={() => this.toggleProvideTag(tag)}
              >
                <Text>{tag}</Text>
              </View>
            ))}
          </View>
          <View className='custom-tag-row'>
            <Input
              className='input-field custom-input'
              placeholder='输入自定义标签'
              value={customProvideInput}
              onInput={(e) => this.setState({ customProvideInput: e.detail.value })}
              onConfirm={this.addCustomProvideTag}
            />
            <Button className='btn-tag-add' onClick={this.addCustomProvideTag}>添加</Button>
          </View>
          {form.provideTags.length > 0 && (
            <View className='selected-tags'>
              <Text className='selected-label'>已选：</Text>
              {form.provideTags.map((tag) => (
                <View key={tag} className='selected-tag provide' onClick={() => this.removeProvideTag(tag)}>
                  <Text>{tag} ✕</Text>
                </View>
              ))}
            </View>
          )}
        </View>

        <View className='form-section glass'>
          <Text className='form-section-title'>我需要 / 需求</Text>
          <View className='tags-grid'>
            {PRESET_NEED_TAGS.map((tag) => (
              <View
                key={tag}
                className={`tag-chip ${form.needTags.includes(tag) ? 'active need' : ''}`}
                onClick={() => this.toggleNeedTag(tag)}
              >
                <Text>{tag}</Text>
              </View>
            ))}
          </View>
          <View className='custom-tag-row'>
            <Input
              className='input-field custom-input'
              placeholder='输入自定义标签'
              value={customNeedInput}
              onInput={(e) => this.setState({ customNeedInput: e.detail.value })}
              onConfirm={this.addCustomNeedTag}
            />
            <Button className='btn-tag-add' onClick={this.addCustomNeedTag}>添加</Button>
          </View>
          {form.needTags.length > 0 && (
            <View className='selected-tags'>
              <Text className='selected-label'>已选：</Text>
              {form.needTags.map((tag) => (
                <View key={tag} className='selected-tag need' onClick={() => this.removeNeedTag(tag)}>
                  <Text>{tag} ✕</Text>
                </View>
              ))}
            </View>
          )}
        </View>

        <View className='step-actions'>
          <Button className='btn-secondary' onClick={this.prevStep}>← 上一步</Button>
          <Button className='btn-primary' onClick={this.nextStep}>下一步：图片上传 →</Button>
        </View>
      </View>
    )
  }

  // ===== 渲染: Step3 图片上传 =====

  renderStep3() {
    const { images } = this.state.form
    return (
      <View className='step-content fade-in'>
        <View className='ai-hint'>
          <Text>🖼️ 上传产品展示图或项目案例，最多9张</Text>
        </View>

        <View className='form-section glass'>
          <Text className='form-section-title'>展示图片（{images.length}/9）</Text>
          <View className='image-picker'>
            {images.map((img, i) => (
              <View key={i} className='image-item'>
                <Image className='image-thumb' src={img} mode='aspectFill' />
                <View className='image-remove' onClick={() => this.removeImage(i)}>✕</View>
              </View>
            ))}
            {images.length < 9 && (
              <View className='image-add' onClick={this.chooseImages}>
                <Text className='add-icon'>+</Text>
                <Text className='add-text'>添加图片</Text>
              </View>
            )}
          </View>
          <Text className='image-hint'>点击添加，支持 JPG / PNG 格式</Text>
        </View>

        <View className='step-actions'>
          <Button className='btn-secondary' onClick={this.prevStep}>← 上一步</Button>
          <Button className='btn-primary' onClick={this.nextStep}>预览确认 →</Button>
        </View>
      </View>
    )
  }

  // ===== 渲染: Step4 预览确认 =====

  renderStep4() {
    const { form, submitting, publishDone } = this.state
    return (
      <View className='step-content fade-in'>
        <View className='preview-header'>
          <Text className='preview-name'>{form.name || '您的姓名'} 的数字名片</Text>
        </View>

        <View className='preview-card glass'>
          <View className='preview-avatar'>
            <Text className='preview-avatar-text'>{form.name ? form.name.charAt(0) : '?'}</Text>
          </View>
          <Text className='preview-user-name'>{form.name || '未填写'}</Text>
          <Text className='preview-company'>
            {form.company || ''}{form.company && form.position ? ' · ' : ''}{form.position || ''}
          </Text>
          {form.bio && <Text className='preview-bio'>{form.bio}</Text>}

          {form.provideTags.length > 0 && (
            <View className='preview-tag-group'>
              <Text className='tag-label'>我能提供</Text>
              <View className='tags'>
                {form.provideTags.map((tag, i) => (
                  <Text key={i} className='tag tag-provide'>{tag}</Text>
                ))}
              </View>
            </View>
          )}

          {form.needTags.length > 0 && (
            <View className='preview-tag-group'>
              <Text className='tag-label'>我需要</Text>
              <View className='tags'>
                {form.needTags.map((tag, i) => (
                  <Text key={i} className='tag tag-need'>{tag}</Text>
                ))}
              </View>
            </View>
          )}

          {form.images.length > 0 && (
            <View className='preview-images'>
              <Text className='preview-images-title'>展示图片（{form.images.length}张）</Text>
              <View className='preview-images-grid'>
                {form.images.map((img, i) => (
                  <Image key={i} className='preview-image' src={img} mode='aspectFill' />
                ))}
              </View>
            </View>
          )}
        </View>

        <View className='step-actions'>
          <Button className='btn-secondary' onClick={this.prevStep}>← 返回编辑</Button>
        </View>

        <View className='publish-actions'>
          <Button
            className='btn-draft'
            onClick={this.saveDraft}
            disabled={submitting || publishDone}
          >
            💾 保存草稿
          </Button>
          <Button
            className='btn-primary publish-btn'
            onClick={this.publish}
            disabled={submitting || publishDone}
            loading={submitting}
          >
            {submitting ? '发布中...' : publishDone ? '已发布 ✓' : '🚀 发布'}
          </Button>
        </View>
      </View>
    )
  }

  // ===== 主渲染 =====

  render() {
    const { step, publishDone } = this.state
    const showBack = !publishDone

    return (
      <View className='editor-page'>
        <NavBar
          title='编辑名片'
          showBack={showBack}
          onBack={publishDone ? undefined : (step > 1 ? this.prevStep : this.goBack)}
        />

        {!publishDone && this.renderStepIndicator()}

        <ScrollView className='editor-content' scrollY>
          {step === 1 && this.renderStep1()}
          {step === 2 && this.renderStep2()}
          {step === 3 && this.renderStep3()}
          {step === 4 && this.renderStep4()}
        </ScrollView>
      </View>
    )
  }
}
