#!/usr/bin/env python3
"""
资源优化对比可视化
"""

import json

def print_comparison():
    print("="*90)
    print("CPU/内存 资源优化对比")
    print("="*90)
    print()
    
    # 方案数据
    schemes = [
        {
            "name": "原始配置",
            "cpu": 8,
            "mem": 10,
            "qps": 13.0,
            "lat": 327,
            "cost": 1100,
        },
        {
            "name": "方案 A (推荐)",
            "cpu": 8,
            "mem": 4,
            "qps": 13.0,
            "lat": 327,
            "cost": 920,
        },
        {
            "name": "方案 B",
            "cpu": 4,
            "mem": 2,
            "qps": 11.5,
            "lat": 350,
            "cost": 460,
        },
        {
            "name": "方案 C",
            "cpu": 2,
            "mem": 2,
            "qps": 6.0,
            "lat": 330,
            "cost": 260,
        },
    ]
    
    # 表头
    print(f"{'方案':<20} {'CPU':>6} {'内存':>8} {'QPS':>8} {'延迟':>10} {'月成本':>10} {'节省':>10}")
    print("-"*90)
    
    base_cost = schemes[0]["cost"]
    
    for s in schemes:
        saved = base_cost - s["cost"] if s["cost"] < base_cost else 0
        saved_pct = f"{saved/base_cost*100:.0f}%" if saved > 0 else "-"
        print(f"{s['name']:<20} {s['cpu']:>6}核 {s['mem']:>6}GB {s['qps']:>8.1f} {s['lat']:>8}ms ¥{s['cost']:>8} {saved_pct:>10}")
    
    print()
    print("="*90)
    print("资源效率分析")
    print("="*90)
    print()
    
    # 效率计算
    print(f"{'方案':<20} {'QPS/核':>10} {'QPS/GB':>10} {'CPU利用率':>12} {'内存利用率':>12}")
    print("-"*90)
    
    for s in schemes[1:]:  # 跳过原始配置
        qps_per_cpu = s["qps"] / s["cpu"]
        qps_per_gb = s["qps"] / s["mem"]
        
        # 假设实际使用
        if s["name"] == "方案 A (推荐)":
            actual_mem = 2.0
            cpu_util = "65% x 8"
            mem_util = f"{actual_mem/s['mem']*100:.0f}% (有余量)"
        elif s["name"] == "方案 B":
            actual_mem = 1.7
            cpu_util = "65% x 4"
            mem_util = f"{actual_mem/s['mem']*100:.0f}%"
        else:
            actual_mem = 1.6
            cpu_util = "65% x 2"
            mem_util = f"{actual_mem/s['mem']*100:.0f}%"
        
        print(f"{s['name']:<20} {qps_per_cpu:>10.2f} {qps_per_gb:>10.2f} {cpu_util:>12} {mem_util:>12}")
    
    print()
    print("="*90)
    print("推荐结论")
    print("="*90)
    print()
    print("🏆 方案 A (8核4GB) - 性能优先推荐")
    print("   • 保持最高性能 (13 QPS)")
    print("   • 内存节省 60% (10GB → 4GB)")
    print("   • 成本节省 16% (¥1100 → ¥920)")
    print()
    print("⚖️  方案 B (4核2GB) - 性价比推荐")
    print("   • 性能损失仅 12% (13 → 11.5 QPS)")
    print("   • 资源节省 50% (8核 → 4核)")
    print("   • 成本节省 58% (¥1100 → ¥460)")
    print()
    print("💡 最佳 CPU/内存 比例: 1 : 0.5 (如 8核配4GB，留有余量)")
    print()
    print("="*90)


def print_deployment_guide():
    print()
    print("快速部署指南")
    print("="*90)
    print()
    print("1. 性能优先部署 (8核4GB):")
    print("   ./benchmark/deploy_with_resources.sh a")
    print()
    print("2. 性价比部署 (4核2GB):")
    print("   ./benchmark/deploy_with_resources.sh b")
    print()
    print("3. 极简部署 (2核2GB):")
    print("   ./benchmark/deploy_with_resources.sh c")
    print()
    print("4. 自定义部署:")
    print("   ./benchmark/deploy_with_resources.sh custom")
    print()
    print("="*90)


if __name__ == "__main__":
    print_comparison()
    print_deployment_guide()
