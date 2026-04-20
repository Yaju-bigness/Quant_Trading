"""
绘图配置
解决中文显示问题
"""
import matplotlib.pyplot as plt
import matplotlib as mpl

def setup_chinese_font():
    """配置中文字体"""
    # macOS 系统常用中文字体（按可用性排序）
    chinese_fonts = [
        'Arial Unicode MS',  # macOS 自带，支持中文
        'PingFang HK',       # 苹方港体
        'Kaiti SC',          # 楷体
        'Lantinghei SC',     # 兰亭黑
        'Heiti TC',          # 黑体繁体
        'STHeiti',           # 华文黑体
        'STFangsong',        # 华文仿宋
        'LiHei Pro',         # 嫘黑
        'Hei',               # 黑体
        'SimHei',            # 黑体 (Windows)
        'Microsoft YaHei',   # 微软雅黑 (Windows)
    ]

    plt.rcParams['font.family'] = chinese_fonts + ['sans-serif']
    plt.rcParams['axes.unicode_minus'] = False  # 解决负号显示问题

    # 设置默认图表样式
    plt.rcParams['figure.figsize'] = (12, 6)
    plt.rcParams['figure.dpi'] = 100
    plt.rcParams['axes.grid'] = True
    plt.rcParams['grid.alpha'] = 0.3

    # 设置字体大小
    plt.rcParams['font.size'] = 10
    plt.rcParams['axes.titlesize'] = 12
    plt.rcParams['axes.labelsize'] = 10
    plt.rcParams['xtick.labelsize'] = 9
    plt.rcParams['ytick.labelsize'] = 9
    plt.rcParams['legend.fontsize'] = 9

    print("中文字体配置完成")


def get_available_chinese_fonts():
    """获取可用的中文字体列表"""
    from matplotlib.font_manager import fontManager

    chinese_keywords = ['song', 'hei', 'kai', 'fang', 'chinese', 'cjk', 'ming', 'yuan', 'ping']

    available_fonts = []
    for font in fontManager.ttflist:
        font_name = font.name.lower()
        if any(kw in font_name for kw in chinese_keywords):
            available_fonts.append(font.name)

    return sorted(set(available_fonts))


if __name__ == '__main__':
    # 测试
    setup_chinese_font()

    print("\n可用的中文字体:")
    fonts = get_available_chinese_fonts()
    for font in fonts[:20]:
        print(f"  - {font}")

    # 测试绘图
    import numpy as np
    fig, ax = plt.subplots(figsize=(8, 4))
    x = np.linspace(0, 10, 100)
    ax.plot(x, np.sin(x), label='正弦曲线')
    ax.plot(x, np.cos(x), label='余弦曲线')
    ax.set_title('中文标题测试')
    ax.set_xlabel('横轴（中文）')
    ax.set_ylabel('纵轴（中文）')
    ax.legend()
    plt.savefig('/Users/yanjun.wang/quant_trading/font_test.png', dpi=100)
    print("\n测试图表已保存: font_test.png")
    plt.show()
